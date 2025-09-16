import asyncio
import base64
import json
import time
from datetime import datetime

from fastapi import APIRouter, Request, WebSocket, Form, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Connect

from app.config.settings import settings
from app.models import get_db, Agent, Tenant, Conversation, ToolCall
from app.services.agent_service import AgentService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.deepgram_service import DeepgramService
from app.utils.twilio_utils import (
    extract_twilio_form_data,
    validate_agent_and_phone,
    create_twilio_conversation,
    build_clean_websocket_url,
)
from app.services.audio_service import AudioService

router = APIRouter()


@router.post("/agent/{agent_id}/voice")
async def handle_agent_voice_call(
        agent_id: str, request: Request, db: Session = Depends(get_db)
):
    """Handle incoming voice calls for specific agent"""

    time.sleep(2)  # Simulate delay for testing

    try:
        # Extract Twilio form data
        twilio_data = await extract_twilio_form_data(request)
        
        # Validate agent and phone number
        agent = validate_agent_and_phone(agent_id, twilio_data["to_number"], db)
        
        # Create conversation
        conversation = create_twilio_conversation(
            agent_id=agent_id,
            agent=agent,
            from_number=twilio_data["from_number"],
            call_sid=twilio_data["call_sid"],
            conversation_type="voice",
            db=db
        )
        
    except HTTPException as e:
        # Return TwiML response for unavailable service or errors
        response = VoiceResponse()
        error_message = "We are sorry, the business you called is not available at the moment. Please try again later."
        if e.status_code == 400:
            error_message = "Invalid request. Please check the number and try again."
        
        response.say(error_message, voice="alice")
        return Response(content=str(response), media_type="application/xml")

    # Create TwiML response with agent-specific WebSocket URL
    response = VoiceResponse()
    connect = Connect()
    connect.stream(
        url=build_clean_websocket_url(settings.BASE_URL, agent_id, conversation.id)
    )
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


@router.post("/agent/{agent_id}/messages")
async def handle_agent_sms(
        agent_id: str,
        from_number: str = Form(..., alias="From"),
        to_number: str = Form(..., alias="To"),
        body: str = Form(..., alias="Body"),
        message_sid: str = Form(..., alias="MessageSid"),
        db: Session = Depends(get_db),
):
    """Handle incoming SMS messages for specific agent"""

    try:
        # Validate agent and phone number
        agent = validate_agent_and_phone(agent_id, to_number, db)
        
        # Create conversation
        conversation = create_twilio_conversation(
            agent_id=agent_id,
            agent=agent,
            from_number=from_number,
            call_sid=message_sid,
            conversation_type="message",
            db=db
        )
        
    except HTTPException as e:
        # Return error response for unavailable service
        from twilio.twiml.messaging_response import MessagingResponse

        response = MessagingResponse()
        error_message = "We are sorry, the business you texted is not available at the moment. Please try again later."
        if e.status_code == 400:
            error_message = "Invalid request. Please check the number and try again."
            
        response.message(error_message)
        return Response(content=str(response), media_type="application/xml")

    # Save incoming message to transcript
    conversation_service = ConversationService(db)
    conversation_service.add_message(conversation.id, "user", body)

    # TODO: Process SMS with AI and respond

    return {
        "message": "SMS received",
        "conversation_id": conversation.id,
        "agent_id": agent_id,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/agent/{agent_id}/callback")
async def handle_agent_callback(
        agent_id: str, request: Request, db: Session = Depends(get_db)
):
    """Handle Twilio callbacks for specific agent"""

    # Verify agent exists and is active
    agent = (
        db.query(Agent)
        .join(Tenant)
        .filter(Agent.id == agent_id, Agent.active, Tenant.active)
        .first()
    )
    if not agent:
        return {
            "status": "callback rejected",
            "reason": "business not available",
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
        }

    form_data = await request.form()
    return {
        "status": "callback received",
        "agent_id": agent_id,
        "data": dict(form_data),
        "timestamp": datetime.now().isoformat(),
    }


@router.websocket("/ws/{agent_id}/twilio/{conversation_id}")
async def agent_websocket_handler(
        websocket: WebSocket, agent_id: str, conversation_id: str
):
    """Handle Twilio WebSocket audio stream for specific agent"""

    await websocket.accept()

    # Get database session
    db_session = None
    conversation = None
    deepgram_ws = None
    tasks = []
    cleanup_completed = False

    try:
        from app.models import get_db_session

        db_session = get_db_session()

        # Get agent from database with active tenant check
        agent = (
            db_session.query(Agent)
            .join(Tenant)
            .filter(Agent.id == agent_id, Agent.active, Tenant.active)
            .first()
        )

        if not agent:
            await websocket.close(code=1008, reason="Business not available")
            return

        # Get or create conversation
        if conversation_id:
            conversation = (
                db_session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )

        if not conversation:
            # Create new conversation if not provided
            conversation_service = ConversationService(db_session)
            conversation = conversation_service.create_conversation(
                agent_id=agent_id,
                tenant_id=agent.tenant_id,
                caller_phone="unknown",
                conversation_type="voice",
                session_name=f"WebSocket call - {agent.name}",
            )
        print(f"Conversation ID: {conversation.id}")
        # Setup communication queues
        audio_queue = asyncio.Queue()
        stream_sid_queue = asyncio.Queue()
        
        # Audio recording variables
        user_audio_buffer = []  # Collect user audio chunks
        agent_audio_buffer = []  # Collect agent audio chunks

        # Create agent service for dynamic configuration
        agent_service = AgentService()
        agent_config = agent_service.build_agent_config(agent)
        # Create Deepgram service
        deepgram_service = DeepgramService(agent_config)

        async with deepgram_service.connect() as dg_connection:
            deepgram_ws = dg_connection
            # Send configuration to Deepgram
            await deepgram_service.send_config(deepgram_ws)

            # Cleanup handler
            async def cleanup_resources():
                """Clean up resources and end conversation"""
                nonlocal cleanup_completed
                if cleanup_completed:
                    return

                cleanup_completed = True
                print("Starting cleanup...")

                # Cancel running tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()

                # Handle unexpected disconnection and generate summary
                try:
                    if conversation and db_session:
                        await handle_unexpected_disconnect(conversation, db_session)

                        # Generate conversation summary
                        await generate_conversation_summary(conversation.id, db_session)

                        print(f"Ended conversation: {conversation.id}")
                except Exception as cleanup_error:
                    print(f"Error ending conversation: {cleanup_error}")

                # Close WebSocket if still open
                try:
                    if not websocket.client_state.DISCONNECTED:
                        await websocket.close()
                        print("WebSocket closed")
                except Exception as ws_error:
                    print(f"Error closing WebSocket: {ws_error}")

            # Define concurrent tasks
            async def audio_sender():
                """Send audio from Twilio to Deepgram"""
                try:
                    while True:
                        audio_chunk = await audio_queue.get()
                        if audio_chunk is None:  # Sentinel value for shutdown
                            break
                        await deepgram_service.send_audio(deepgram_ws, audio_chunk)
                except asyncio.CancelledError:
                    print("Audio sender cancelled")
                except Exception as sender_error:
                    print(f"Audio sender error: {sender_error}")
                    await cleanup_resources()

            async def deepgram_receiver():
                """Receive responses from Deepgram and forward to Twilio"""
                try:
                    stream_sid = await stream_sid_queue.get()
                    conv_service = ConversationService(db_session)

                    async for message in deepgram_ws:

                        try:
                            if isinstance(message, str):
                                # Parse the message to detect type
                                message_json = json.loads(message)
                                message_type = message_json.get("type")

                                # Handle FunctionCallRequest messages
                                if message_type == "FunctionCallRequest":
                                    await handle_function_call_request(
                                        message_json,
                                        deepgram_ws,
                                        conversation,
                                        db_session
                                    )
                                    continue

                                # Handle ConversationText messages - Store structured messages
                                if message_type == "ConversationText":
                                    await handle_conversation_text(
                                        message_json,
                                        conversation,
                                        db_session,
                                        user_audio_buffer,
                                        agent_audio_buffer,
                                    )
                                    continue

                                # Handle other text messages
                                event = DeepgramService.parse_message(message)
                                await handle_deepgram_event(
                                    event,
                                    websocket,
                                    stream_sid,
                                    conversation,
                                    deepgram_ws,
                                    conv_service,
                                    db_session,
                                    deepgram_service,
                                    user_audio_buffer,
                                    agent_audio_buffer,
                                )
                                continue

                            # Handle binary audio data
                            # Collect agent audio for recording
                            agent_audio_buffer.append(message)
                            
                            media_message = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": base64.b64encode(message).decode("ascii")
                                },
                            }
                            await websocket.send_text(json.dumps(media_message))

                        except Exception as receiver_error:
                            print(f"Deepgram message error: {receiver_error}")
                            continue

                except asyncio.CancelledError:
                    print("Deepgram receiver cancelled")
                except Exception as receiver_error:
                    print(f"Deepgram receiver error: {receiver_error}")
                    await cleanup_resources()

            async def twilio_receiver():
                """Receive audio from Twilio and queue for Deepgram"""
                audio_buffer = bytearray()

                try:
                    async for message in websocket.iter_text():
                        try:
                            data = json.loads(message)

                            if data.get("event") == "start":
                                stream_sid = data["start"]["streamSid"]
                                stream_sid_queue.put_nowait(stream_sid)
                                print(f"Call started: {stream_sid}")

                            elif data.get("event") == "media":
                                media = data["media"]
                                if media.get("track") == "inbound":
                                    audio_chunk = base64.b64decode(media["payload"])
                                    audio_buffer.extend(audio_chunk)
                                    # Also collect for user audio recording
                                    user_audio_buffer.append(audio_chunk)

                            elif data.get("event") == "stop":
                                print("Call stop event received")
                                # Signal audio sender to stop
                                audio_queue.put_nowait(None)
                                await cleanup_resources()
                                break

                            # Send buffered audio when we have enough
                            while len(audio_buffer) >= settings.BUFFER_SIZE:
                                chunk = audio_buffer[: settings.BUFFER_SIZE]
                                audio_queue.put_nowait(chunk)
                                audio_buffer = audio_buffer[settings.BUFFER_SIZE:]

                        except json.JSONDecodeError:
                            print("Invalid JSON received from Twilio")
                            continue
                        except Exception as msg_error:
                            print(f"Twilio message error: {msg_error}")
                            continue

                except asyncio.CancelledError:
                    print("Twilio receiver cancelled")
                except Exception as twilio_error:
                    print(f"Twilio receiver error: {twilio_error}")
                    await cleanup_resources()

            # Create and store tasks
            tasks.extend([
                asyncio.create_task(audio_sender()),
                asyncio.create_task(deepgram_receiver()),
                asyncio.create_task(twilio_receiver())
            ])

            # Run all tasks concurrently
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await cleanup_resources()

    except Exception as e:
        print(f"WebSocket handler error: {e}")
    finally:
        if db_session:
            db_session.close()


async def handle_deepgram_event(
        event: dict,
        websocket: WebSocket,
        stream_sid: str,
        conversation: Conversation,
        deepgram_ws,
        conversation_service: ConversationService,
        db_session: Session,
        deepgram_service: DeepgramService = None,
        user_audio_buffer: list = None,
        agent_audio_buffer: list = None,
):
    """Handle different types of events from Deepgram"""

    event_type = event.get("type")

    if event_type == "Transcript" and event.get("is_final"):
        # Defer message creation and audio saving to ConversationText handler
        # This prevents consuming the first audio buffer too early and ensures
        # audio aligns with the exact message that Deepgram produces.
        transcript_text = event.get("transcript", "")
        if transcript_text:
            print(f"📝 Final transcript received (deferred save): {transcript_text[:80]}...")
        return

    elif event_type == "UserStartedSpeaking":
        # Handle barge-in: clear Twilio's audio buffer
        clear_message = {"event": "clear", "streamSid": stream_sid}
        await websocket.send_text(json.dumps(clear_message))

    elif event_type == "RequestTool":
        # Handle tool execution requests
        tool_info = event.get("tool", {})
        tool_name = tool_info.get("name")
        tool_args = tool_info.get("arguments", {})

        if tool_name:
            # Execute tool with tenant context
            result = await execute_tenant_tool(
                tool_name, tool_args, conversation, db_session
            )

            # Send result back to Deepgram
            if deepgram_service:
                await deepgram_service.send_tool_result(deepgram_ws, tool_name, result)

    elif event_type == "SpeechStarted":
        # Do not create/save a message here. Deepgram will emit a ConversationText
        # for the assistant utterance shortly after audio begins. We keep buffering
        # audio and let handle_conversation_text persist it with the correct message_id.
        speech_text = event.get("speech", "")
        if speech_text:
            print(f"🗣️ Agent started speaking (deferred save). Preview: {speech_text[:60]}...")
        return


async def execute_tenant_tool(
        tool_name: str, tool_args: dict, conversation: Conversation, db_session: Session
) -> dict:
    """Execute a tool within the tenant context with enhanced logging"""
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    tool_call = None
    start_time = time.time()
    
    try:
        from app.config.agent_functions import FUNCTION_MAP

        # Check if tool exists
        if tool_name not in FUNCTION_MAP:
            logger.error(f"Tool '{tool_name}' not found in FUNCTION_MAP")
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        # Log function call received
        print(f"🔧 execute_tenant_tool called with: {tool_name}")
        print(f"🔧 Tool args: {tool_args}")
        logger.info(f"Function call received: {tool_name}")
        logger.info(f"Parameters: {tool_args}")

        # Add tenant and agent context for knowledge base tools
        if tool_name in ["search_agent_dataset", "search_business_knowledge_base"]:
            tool_args["tenant_id"] = conversation.tenant_id
            tool_args["agent_id"] = conversation.agent_id
            print(f"🔧 Enhanced tool_args for knowledge base: {tool_args}")

        # Add agent context for calendar tools
        elif tool_name in ["create_calendar_event", "list_calendar_events", "cancel_calendar_event", "search_calendar_events", "update_calendar_event"]:
            tool_args["agent_id"] = conversation.agent_id
            print(f"🔧 Enhanced tool_args for calendar: {tool_args}")

        # Log tool call start to database
        tool_call = ToolCall(
            conversation_id=conversation.id,
            tool_name=tool_name,
            parameters=tool_args,
            status="pending",
        )
        db_session.add(tool_call)
        db_session.commit()

        # Execute the tool function
        tool_function = FUNCTION_MAP[tool_name]
        print(f"🔧 Found tool function: {tool_function}")

        if tool_name in ["search_agent_dataset", "search_business_knowledge_base"]:
            # Call with explicit parameters for knowledge base tools
            print(f"🔧 Calling {tool_name} with parameters:")
            print(f"🔧   tenant_id: {tool_args.get('tenant_id')}")
            print(f"🔧   agent_id: {tool_args.get('agent_id')}")
            print(f"🔧   label: {tool_args.get('label')}")
            print(f"🔧   query: {tool_args.get('query', '')}")

            result = await tool_function(
                tenant_id=tool_args.get("tenant_id"),
                agent_id=tool_args.get("agent_id"),
                label=tool_args.get("label"),
                query=tool_args.get("query", ""),
                top_k=tool_args.get("top_k", 5),
                return_all=tool_args.get("return_all", False)
            )
            print(f"🔧 {tool_name} returned: {result}")
        elif tool_name == "hangup_function":
            # Special handling for hangup function
            print("🔧 Hangup function called - preparing to close connection")
            result = await tool_function(**tool_args)
            print(f"🔧 hangup_function returned: {result}")
            
            # Mark the result with a special signal for the caller to handle connection closure
            if isinstance(result, dict) and result.get("action") == "hangup":
                result["_trigger_close"] = True
                print("🔧 Hangup signal added to result - connection should be closed")
        else:
            # For other tools, pass all args
            result = await tool_function(**tool_args)

        # Calculate execution time
        execution_time = time.time() - start_time
        logger.info(f"Function Execution Latency: {execution_time:.3f}s")
        logger.info(f"Function response: {result}")

        # Update tool call with result and execution time
        tool_call.result = result
        tool_call.status = "success" if result.get("success") else "failed"
        # Add execution time to the result for tracking
        if isinstance(result, dict):
            result["execution_time"] = execution_time
        db_session.commit()

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Error executing function: {str(e)}")
        logger.info(f"Function Execution Latency (failed): {execution_time:.3f}s")
        
        # Log tool call failure
        if tool_call:
            tool_call.result = {"error": str(e), "execution_time": execution_time}
            tool_call.status = "failed"
            db_session.commit()

        return {"success": False, "error": str(e), "execution_time": execution_time}


async def handle_function_call_request(
    message_json: dict,
    deepgram_ws,
    conversation: Conversation,
    db_session: Session
):
    """Handle FunctionCallRequest messages from Deepgram"""
    import logging

    logger = logging.getLogger(__name__)

    function_call_id = None
    try:
        # Extract function call information
        functions = message_json.get("functions", [])
        if not functions:
            logger.error("No functions found in FunctionCallRequest")
            return

        function_info = functions[0]
        function_name = function_info.get("name")
        function_call_id = function_info.get("id")
        client_side = function_info.get("client_side", False)

        print(f"🔍 Function info: name={function_name}, id={function_call_id}, client_side={client_side}")

        # Parse arguments - they come as a JSON string
        arguments_str = function_info.get("arguments", "{}")
        try:
            parameters = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
        except json.JSONDecodeError:
            logger.error(f"Failed to parse function arguments: {arguments_str}")
            parameters = {}

        print(f"🔍 Function call received: {function_name} with ID: {function_call_id}")
        print(f"🔍 Raw parameters: {parameters}")

        # Add tenant and agent context for knowledge base tools
        if function_name in ["search_agent_dataset", "search_business_knowledge_base"]:
            parameters["tenant_id"] = conversation.tenant_id
            parameters["agent_id"] = conversation.agent_id
            print(f"🔍 Enhanced parameters for knowledge base: {parameters}")

        # Add agent context for calendar tools
        elif function_name in ["create_calendar_event", "list_calendar_events", "cancel_calendar_event", "search_calendar_events", "update_calendar_event"]:
            parameters["agent_id"] = conversation.agent_id
            print(f"🔍 Enhanced parameters for calendar: {parameters}")

        # Execute the function using the existing execute_tenant_tool
        print(f"🔍 Executing function: {function_name}")
        result = await execute_tenant_tool(
            function_name, parameters, conversation, db_session
        )
        print(f"🔍 Function execution result: {result}")

        # Create FunctionCallResponse message for Deepgram (matching learn.py format)
        response_message = {
            "type": "FunctionCallResponse",
            "id": function_call_id,
            "name": function_name,
            "content": json.dumps(result) if isinstance(result, dict) else str(result)
        }
        print(f"🔍 Sending FunctionCallResponse: {response_message}")

        # Send response back to Deepgram
        await deepgram_ws.send(json.dumps(response_message))
        print(f"🔍 Successfully sent FunctionCallResponse for {function_name} with ID: {function_call_id}")

        # Check if this is a hangup request - if so, send Close message to Deepgram
        if isinstance(result, dict) and result.get("_trigger_close"):
            print("🔍 Hangup signal detected - sending Close message to Deepgram")
            close_message = {"type": "Close"}
            await deepgram_ws.send(json.dumps(close_message))
            print("🔍 Close message sent to Deepgram - connection should terminate")

        logger.info(f"Function call received: {function_name} with ID: {function_call_id}")
        logger.info(f"Parameters: {parameters}")
        logger.info(f"Function result: {result}")
        logger.info(f"Sent FunctionCallResponse for {function_name} with ID: {function_call_id}")

    except Exception as e:
        logger.error(f"Error handling function call request: {str(e)}")

        # Send error response back to Deepgram
        if function_call_id:
            error_response = {
                "type": "FunctionCallResponse",
                "id": function_call_id,
                "name": function_name if 'function_name' in locals() else "unknown",
                "content": json.dumps({"success": False, "error": str(e)})
            }
            try:
                await deepgram_ws.send(json.dumps(error_response))
            except Exception as send_error:
                logger.error(f"Failed to send error response: {send_error}")


async def handle_conversation_text(
    message_json: dict,
    conversation: Conversation,
    db_session: Session,
    user_audio_buffer: list | None = None,
    agent_audio_buffer: list | None = None,
):
    """Handle ConversationText messages from Deepgram, store them, and non-blockingly persist audio"""
    import logging

    logger = logging.getLogger(__name__)

    async def persist_audio_for_message(conversation_id: str, message_id: str, role: str, chunks: list[bytes]):
        try:
            # Save to disk
            path = AudioService.save_audio_chunks(
                audio_chunks=chunks,
                conversation_id=conversation_id,
                message_id=message_id,
                role=role,
            )
            if path:
                # Update DB with audio path
                MessageService(db_session).update_message_audio(message_id, path)
        except Exception as e:
            print(f"❌ Error in persist_audio_for_message: {e}")

    try:
        role = message_json.get("role", "unknown")  # "user" or "assistant"
        content = message_json.get("content", "")

        if not content.strip():
            print(f"💬 Skipping empty message from {role}")
            return

        print(f"💬 Storing ConversationText: {role} -> {content[:100]}...")

        # Create message service
        message_service = MessageService(db_session)

        # Store the message chronologically and get the created message
        message = message_service.add_message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            message_type="conversation"
        )

        # Non-blocking audio persistence tied to this message
        if role == "user" and user_audio_buffer and len(user_audio_buffer) > 0:
            chunks = user_audio_buffer.copy()
            user_audio_buffer.clear()
            asyncio.create_task(persist_audio_for_message(conversation.id, message.id, role, chunks))
        elif role == "assistant" and agent_audio_buffer and len(agent_audio_buffer) > 0:
            chunks = agent_audio_buffer.copy()
            agent_audio_buffer.clear()
            asyncio.create_task(persist_audio_for_message(conversation.id, message.id, role, chunks))

        logger.info(f"Stored ConversationText message: {role} -> {content[:50]}... (id={message.id})")

    except Exception as e:
        logger.error(f"Error handling ConversationText: {str(e)}")
        print(f"❌ Error storing ConversationText: {str(e)}")




async def handle_connection_timeout(websocket, conversation: Conversation, db_session: Session):
    """Handle user inactivity timeout"""
    print("⏰ User inactivity detected - initiating graceful hangup")

    # Add a system message about timeout
    message_service = MessageService(db_session)
    message_service.add_message(
        conversation_id=conversation.id,
        role="system",
        content="Call ended due to user inactivity",
        message_type="system"
    )

    # Close the connection gracefully
    try:
        await websocket.close(code=1000, reason="User inactivity timeout")
    except Exception as e:
        print(f"Error closing WebSocket: {e}")


async def handle_unexpected_disconnect(conversation: Conversation, db_session: Session):
    """Handle unexpected connection closure"""
    print("⚠️ Unexpected connection closure detected")

    # Add a system message about unexpected closure
    message_service = MessageService(db_session)
    message_service.add_message(
        conversation_id=conversation.id,
        role="system",
        content="Call ended unexpectedly",
        message_type="system"
    )

    # End the conversation
    conv_service = ConversationService(db_session)
    conv_service.end_conversation(conversation.id)


async def generate_conversation_summary(conversation_id: str, db_session: Session):
    """Generate and store conversation summary using LLM"""
    try:
        from app.services.summarization_service import SummarizationService

        print(f"📝 Generating summary for conversation {conversation_id}")

        # Create summarization service
        summarization_service = SummarizationService(db_session)

        # Generate summary
        summary_data = await summarization_service.summarize_conversation(conversation_id)

        if summary_data and not summary_data.get('error'):
            # Store summary in conversation table
            await summarization_service.store_summary_in_conversation(conversation_id, summary_data)
            print(f"✅ Successfully generated and stored summary for {conversation_id}")
        else:
            print(f"⚠️ Summary generation failed for {conversation_id}")

    except Exception as e:
        print(f"❌ Error generating conversation summary: {str(e)}")


async def send_inactivity_warning(deepgram_ws):
    """Send 'Are you there?' message when user is silent for 5 seconds"""
    try:
        # Send a text injection to make Deepgram speak
        warning_message = {
            "type": "Injection",
            "text": "Are you there? Is there anything else I can help you with?"
        }

        await deepgram_ws.send(json.dumps(warning_message))
        print("🗣️ Sent inactivity warning: 'Are you there?'")

    except Exception as e:
        print(f"❌ Error sending inactivity warning: {str(e)}")


async def send_goodbye_message(deepgram_ws):
    """Send goodbye message before hanging up"""
    try:
        # Send goodbye through Deepgram
        goodbye_message = {
            "type": "Injection",
            "text": "Thank you for calling! Have a great day. Goodbye!"
        }

        await deepgram_ws.send(json.dumps(goodbye_message))
        print("👋 Sent goodbye message")

        # Give time for message to be spoken before hangup
        await asyncio.sleep(2)

    except Exception as e:
        print(f"❌ Error sending goodbye message: {str(e)}")
