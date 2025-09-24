import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Request, WebSocket, Form, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Connect

from app.config.settings import settings
from app.models import Agent, Conversation, ToolCall, Message, get_db
from app.services.audio_service import AudioService
from app.services.conversation_service import ConversationService
from app.services.order_service import OrderService
from app.tools.registry import global_registry
from app.utils.logging_config import app_logger as logger
from app.utils.twilio_utils import (
    extract_twilio_form_data,
    validate_agent_and_phone,
    create_twilio_conversation,
    build_clean_websocket_url,
)
from app.websocket.session_manager import WebSocketSession

router = APIRouter()


@router.post("/{agent_id}/voice")
async def handle_agent_voice_call(
    agent_id: str, request: Request, db: Session = Depends(get_db)
):
    """Handle incoming voice calls for specific agent"""

    logger.info("[VOICE] Incoming call for agent %s", agent_id)

    try:
        twilio_data = await extract_twilio_form_data(request)
        logger.debug("[VOICE] Twilio data: %s", twilio_data)

        agent = validate_agent_and_phone(agent_id, twilio_data["to_number"], db)
        logger.info("[VOICE] Agent validated: %s (%s)", agent.name, agent.id)

        conversation = create_twilio_conversation(
            agent_id=agent_id,
            agent=agent,
            from_number=twilio_data["from_number"],
            call_sid=twilio_data["call_sid"],
            conversation_type="voice",
            db=db,
        )

        try:
            order_service = OrderService()
            order_service.db = db  # Set the database session
            order_service.create_preemptive_order(conversation)
            logger.info(
                "[ORDER] Preemptive order created for conversation %s", conversation.id
            )
        except Exception as order_error:
            logger.error(
                "[ORDER] Failed to create preemptive order for conversation %s: %s",
                conversation.id,
                str(order_error),
            )
            # Don't fail the call if order creation fails

        logger.info("[VOICE] Conversation created: %s", conversation.id)

    except HTTPException as e:
        logger.error("[VOICE] HTTPException: %s - %s", e.status_code, e.detail)
        response = VoiceResponse()
        error_message = "We are sorry, the business you called is not available at the moment. Please try again later."
        if e.status_code == 404:
            error_message = "The number you have called is not in service."
        elif e.status_code == 400:
            error_message = "Invalid request. Please check the number and try again."

        response.say(error_message, voice="alice")
        logger.debug("[VOICE] Error TwiML: %s", str(response))
        return Response(content=str(response), media_type="application/xml")

    websocket_url = build_clean_websocket_url(
        settings.BASE_URL, agent_id, conversation.id
    )
    logger.debug("[VOICE] WebSocket URL: %s", websocket_url)

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)

    twiml_content = str(response)
    logger.debug("[VOICE] TwiML response: %s", twiml_content)

    return Response(content=twiml_content, media_type="application/xml")


@router.post("/{agent_id}/messages")
async def handle_agent_sms(
    agent_id: str,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle incoming SMS messages for specific agent"""
    logger.info("[SMS] Incoming SMS for agent %s from %s", agent_id, From)

    twilio_data = {
        "from_number": From,
        "to_number": To,
        "call_sid": f"sms_{int(time.time())}",
    }
    body = Body.strip()

    try:
        agent = validate_agent_and_phone(agent_id, twilio_data["to_number"], db)
        logger.info("[SMS] Agent validated: %s", agent.name)

        conversation = create_twilio_conversation(
            agent_id=agent_id,
            agent=agent,
            from_number=twilio_data["from_number"],
            call_sid=twilio_data["call_sid"],
            conversation_type="sms",
            db=db,
        )
        logger.info("[SMS] Conversation created/found: %s", conversation.id)

    except HTTPException as e:
        logger.error("[SMS] Error validating agent for SMS: %s", e.detail)
        return Response(status_code=e.status_code, content=e.detail)

    conversation_service = ConversationService(db)
    conversation_service.add_message(conversation.id, "user", body)

    logger.debug(
        "SMS processing not implemented yet for conversation %s", conversation.id
    )

    return {"message": "SMS received", "conversation_id": conversation.id}


@router.post("/{agent_id}/callback")
async def handle_agent_callback(
    agent_id: str, request: Request, db: Session = Depends(get_db)
):
    """Handle Twilio callbacks for specific agent"""
    logger.info("[CALLBACK] Received callback for agent %s", agent_id)

    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        logger.warning("[CALLBACK] Agent %s not found or inactive", agent_id)
        raise HTTPException(status_code=404, detail="Agent not found")

    form_data = await request.form()
    call_status = form_data.get("CallStatus")
    call_sid = form_data.get("CallSid")
    logger.info("[CALLBACK] Call %s status: %s", call_sid, call_status)

    return Response(status_code=200)


@router.websocket("/ws/{agent_id}/twilio/{conversation_id}")
async def agent_websocket_handler(
    websocket: WebSocket,
    agent_id: str,
    conversation_id: str,
):
    """Handle Twilio WebSocket audio stream for specific agent - Refactored Version"""
    logger.info(
        "[WS] WebSocket connection request for agent %s, conversation %s",
        agent_id,
        conversation_id,
    )
    await websocket.accept()
    logger.info("[WS] WebSocket connection accepted")

    db_session = None
    session = None

    try:
        # Get database session
        db_session = next(get_db())

        # Create and setup WebSocket session
        session = WebSocketSession(websocket, agent_id, conversation_id, db_session)

        # Setup all components (validation, configuration, services)
        if not await session.setup():
            logger.error("[WS] Session setup failed")
            return

        # Start processing (Deepgram connection, message handling, audio streaming)
        await session.start_processing()

    except Exception as e:
        logger.exception(f"[WS] WebSocket handler error: {e}")
    finally:
        # Cleanup is handled by the session manager
        if session:
            await session.cleanup()
        if db_session:
            db_session.close()
        logger.info("[WS] WebSocket handler completed")


async def handle_deepgram_event(
    event: dict,
    conversation: Conversation,
    db_session: Session,
    user_audio_buffer: Optional[List[bytes]] = None,
    agent_audio_buffer: Optional[List[bytes]] = None,
):
    """Handle non-text events from Deepgram."""
    event_type = event.get("type")
    logger.debug("Handling Deepgram event: %s", event_type)

    if event_type == "UserEndedSpeaking":
        if user_audio_buffer:
            logger.info(
                "User stopped speaking. Final transcript will be saved with audio."
            )
        return
    elif event_type == "AgentEndedSpeaking":
        if agent_audio_buffer:
            logger.info(
                "Agent stopped speaking. Final speech will be saved with audio."
            )
        return
    elif event_type == "UserStartedSpeaking":
        logger.info("User started speaking.")
        return
    elif event_type == "SpeechStarted":
        logger.info("Agent started speaking.")
        return


async def execute_tenant_tool(
    tool_name: str, tool_args: dict, conversation: Conversation, db_session: Session
) -> dict:
    """Execute a tool within the tenant context using the unified registry."""
    tool_call = None
    start_time = time.time()
    try:
        # Check if tool exists in the unified registry
        if tool_name not in global_registry.tools:
            logger.error("Tool '%s' not found in registry", tool_name)
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        logger.info("Function call received: %s with params: %s", tool_name, tool_args)

        # Add agent_id for tools that need it
        if tool_name in ["search_collection"]:
            tool_args["agent_id"] = conversation.agent_id
        elif tool_name in [
            "create_calendar_event",
            "list_calendar_events",
            "cancel_calendar_event",
            "search_calendar_events",
            "update_calendar_event",
        ]:
            tool_args["agent_id"] = conversation.agent_id

        # Create tool call record
        tool_call = ToolCall(
            conversation_id=conversation.id,
            tool_name=tool_name,
            parameters=tool_args,
            status="started",
        )
        db_session.add(tool_call)
        db_session.commit()

        # Execute the tool using the registry
        result = await global_registry.execute_tool(
            tool_name, tool_args, conversation.id
        )

        if isinstance(result, dict) and result.get("action") == "hangup":
            result["_trigger_close"] = True

        execution_time = time.time() - start_time
        logger.info(
            "Function %s executed in %.3fs. Result: %s",
            tool_name,
            execution_time,
            result,
        )

        tool_call.result = result
        tool_call.status = "completed"
        tool_call.execution_time = execution_time
        db_session.commit()

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        logger.exception("Error executing function '%s': %s", tool_name, e)
        if tool_call:
            tool_call.result = {"error": str(e)}
            tool_call.status = "failed"
            tool_call.execution_time = execution_time
            db_session.commit()
        return {"success": False, "error": str(e)}


async def handle_function_call_request(
    message_json: dict, deepgram_ws, conversation: Conversation, db_session: Session
):
    """Handle FunctionCallRequest messages from Deepgram."""
    function_call_id = None
    function_name = None
    try:
        functions = message_json.get("functions", [])
        if not functions:
            logger.error("No functions found in FunctionCallRequest")
            return

        function_info = functions[0]
        function_name = function_info.get("name")
        function_call_id = function_info.get("id")
        arguments_str = function_info.get("arguments", "{}")

        try:
            parameters = json.loads(arguments_str)
        except json.JSONDecodeError:
            logger.error("Failed to parse function arguments: %s", arguments_str)
            parameters = {}

        result = await execute_tenant_tool(
            function_name, parameters, conversation, db_session
        )

        response_message = {
            "type": "FunctionCallResponse",
            "id": function_call_id,
            "name": function_name,
            "content": json.dumps(result) if isinstance(result, dict) else str(result),
        }
        await deepgram_ws.send(json.dumps(response_message))

        if isinstance(result, dict) and result.get("_trigger_close"):
            logger.info("Hangup signal detected - sending Close message to Deepgram")
            await deepgram_ws.send(json.dumps({"type": "Close"}))

    except Exception as e:
        logger.exception("Error handling function call request: %s", e)
        if function_call_id:
            error_response = {
                "type": "FunctionCallResponse",
                "id": function_call_id,
                "name": function_name or "unknown",
                "content": json.dumps({"success": False, "error": str(e)}),
            }
            try:
                await deepgram_ws.send(json.dumps(error_response))
            except Exception as send_error:
                logger.error("Failed to send error response: %s", send_error)


async def handle_conversation_text(
    message_json: dict,
    conversation: Conversation,
    db_session: Session,
    user_audio_buffer: Optional[List[bytes]] = None,
    agent_audio_buffer: Optional[List[bytes]] = None,
):
    """Handle ConversationText messages from Deepgram and persist them."""

    async def persist_audio_for_message(
        conv_id: str, msg_id: str, role: str, chunks: list[bytes]
    ):
        try:
            if not chunks:
                return
            # Use AudioService static method to save audio chunks
            path = AudioService.save_audio_chunks(
                audio_chunks=chunks,
                conversation_id=conv_id,
                message_id=msg_id,
                role=role,
            )

            # Update message with audio path
            message_model = (
                db_session.query(Message).filter(Message.id == msg_id).first()
            )
            if message_model:
                message_model.audio_file_path = path
                message_model.updated_at = datetime.now(timezone.utc)
                db_session.commit()
        except Exception as e:
            logger.exception("Error in persist_audio_for_message: %s", e)

    try:
        role = message_json.get("role", "unknown")
        content = message_json.get("content", "")
        if not content.strip():
            return

        logger.info("Storing ConversationText: %s -> %s...", role, content[:100])

        # Get the next sequence number for this conversation
        max_sequence = (
            db_session.query(func.max(Message.sequence_number))
            .filter(Message.conversation_id == conversation.id)
            .scalar()
        ) or 0

        # Create new message directly
        message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role=role,
            content=content,
            sequence_number=max_sequence + 1,
            message_type="conversation",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db_session.add(message)
        db_session.commit()
        db_session.refresh(message)

        if role == "user" and user_audio_buffer:
            chunks = list(user_audio_buffer)
            user_audio_buffer.clear()
            asyncio.create_task(
                persist_audio_for_message(conversation.id, message.id, role, chunks)
            )
        elif role == "assistant" and agent_audio_buffer:
            chunks = list(agent_audio_buffer)
            agent_audio_buffer.clear()
            asyncio.create_task(
                persist_audio_for_message(conversation.id, message.id, role, chunks)
            )

    except Exception as e:
        logger.exception("Error handling ConversationText: %s", e)
