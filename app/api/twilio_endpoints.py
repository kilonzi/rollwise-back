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
from app.services.deepgram_service import DeepgramService

router = APIRouter()


@router.post("/agent/{agent_id}/voice")
async def handle_agent_voice_call(
        agent_id: str, request: Request, db: Session = Depends(get_db)
):
    """Handle incoming voice calls for specific agent"""

    # Get agent from database with active tenant check
    agent = (
        db.query(Agent)
        .join(Tenant)
        .filter(Agent.id == agent_id, Agent.active)
        .first()
    )

    time.sleep(3)  # Simulate delay for testing
    if not agent:
        # Return TwiML response for unavailable service
        response = VoiceResponse()
        response.say(
            "We are sorry, the business you called is not available at the moment. Please try again later.",
            voice="alice",
        )
        return Response(content=str(response), media_type="application/xml")

    # Get form data from Twilio
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")
    if to_number != agent.phone_number:
        raise HTTPException(status_code=400, detail="Phone number mismatch")

    # Create conversation
    conversation_service = ConversationService(db)
    conversation = conversation_service.create_conversation(
        agent_id=agent_id,
        tenant_id=str(agent.tenant_id),
        caller_phone=from_number,
        conversation_type="voice",
        twilio_sid=call_sid,
        session_name=f"Voice call from {from_number}",
    )

    # Create TwiML response with agent-specific WebSocket URL
    response = VoiceResponse()
    connect = Connect()
    connect.stream(
        url=f"wss://{settings.BASE_URL}/ws/{agent_id}/twilio?conversation_id={conversation.id}"
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

    # Get agent from database with active tenant check
    agent = (
        db.query(Agent)
        .join(Tenant)
        .filter(Agent.id == agent_id, Agent.active, Tenant.active)
        .first()
    )

    if not agent:
        # Return error response for unavailable service
        from twilio.twiml.messaging_response import MessagingResponse

        response = MessagingResponse()
        response.message(
            "We are sorry, the business you texted is not available at the moment. Please try again later."
        )
        return Response(content=str(response), media_type="application/xml")

    # Verify phone number matches
    if to_number != agent.phone_number:
        raise HTTPException(status_code=400, detail="Phone number mismatch")

    # Create conversation
    conversation_service = ConversationService(db)
    conversation = conversation_service.create_conversation(
        agent_id=agent_id,
        tenant_id=str(agent.tenant_id),
        caller_phone=from_number,
        conversation_type="message",
        twilio_sid=message_sid,
        session_name=f"SMS from {from_number}",
    )

    # Save incoming message to transcript
    conversation_service.add_to_transcript(conversation.id, "user", body)

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


@router.websocket("/ws/{agent_id}/twilio")
async def agent_websocket_handler(
        websocket: WebSocket, agent_id: str, conversation_id: str = None
):
    """Handle Twilio WebSocket audio stream for specific agent"""

    await websocket.accept()

    # Get database session
    db_session = None
    agent = None
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

        # Setup communication queues
        audio_queue = asyncio.Queue()
        stream_sid_queue = asyncio.Queue()

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

                # End conversation
                try:
                    if conversation and db_session:
                        conv_service = ConversationService(db_session)
                        conv_service.end_conversation(conversation.id)
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
                                # Handle text messages
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
                                )
                                continue

                            # Handle binary audio data
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
):
    """Handle different types of events from Deepgram"""

    event_type = event.get("type")

    if event_type == "Transcript" and event.get("is_final"):
        # Save user transcript
        transcript_text = event.get("transcript", "")
        conversation_service.add_to_transcript(conversation.id, "user", transcript_text)

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
        # Agent started speaking - save to transcript
        speech_text = event.get("speech", "")
        if speech_text:
            conversation_service.add_to_transcript(
                conversation.id, "agent", speech_text
            )


async def execute_tenant_tool(
        tool_name: str, tool_args: dict, conversation: Conversation, db_session: Session
) -> dict:
    """Execute a tool within the tenant context"""

    tool_call = None
    try:
        from app.config.agent_functions import FUNCTION_MAP

        # Check if tool exists
        if tool_name not in FUNCTION_MAP:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        # Add tenant and agent context for search_agent_dataset
        if tool_name == "search_agent_dataset":
            tool_args["tenant_id"] = conversation.tenant_id
            tool_args["agent_id"] = conversation.agent_id

        # Log tool call start
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

        if tool_name == "search_agent_dataset":
            # Call with explicit parameters
            result = await tool_function(
                tenant_id=tool_args.get("tenant_id"),
                agent_id=tool_args.get("agent_id"),
                label=tool_args.get("label"),
                query=tool_args.get("query", ""),
                top_k=tool_args.get("top_k", 5),
                return_all=tool_args.get("return_all", False)
            )
        else:
            # For other tools, pass all args
            result = await tool_function(**tool_args)

        # Update tool call with result
        tool_call.result = result
        tool_call.status = "success" if result.get("success") else "failed"
        db_session.commit()

        return result

    except Exception as e:
        # Log tool call failure
        if tool_call:
            tool_call.result = {"error": str(e)}
            tool_call.status = "failed"
            db_session.commit()

        return {"success": False, "error": str(e)}
