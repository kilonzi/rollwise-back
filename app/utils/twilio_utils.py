from typing import Dict
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from app.models import Agent, Conversation
from app.services.conversation_service import ConversationService


async def extract_twilio_form_data(request: Request) -> Dict[str, str]:
    """
    Extract form data from Twilio request.

    Args:
        request: FastAPI Request object

    Returns:
        Dict containing call_sid, from_number, to_number
    """
    form_data = await request.form()
    return {
        "call_sid": form_data.get("CallSid", ""),
        "from_number": form_data.get("From", ""),
        "to_number": form_data.get("To", ""),
    }


def validate_agent_and_phone(agent_id: str, to_number: str, db: Session) -> type[Agent]:
    """
    Validate agent exists, is active, and phone number matches.

    Args:
        agent_id: Agent ID to validate
        to_number: Phone number from Twilio request
        db: Database session

    Returns:
        Agent object if valid

    Raises:
        HTTPException if validation fails
    """
    # Get agent from database with active tenant check
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    if to_number != agent.phone_number:
        raise HTTPException(status_code=400, detail="Phone number mismatch")

    return agent


def create_twilio_conversation(
    agent_id: str,
    agent: Agent,
    from_number: str,
    call_sid: str,
    conversation_type: str,
    db: Session,
) -> Conversation:
    """
    Create a new conversation for Twilio interaction.

    Args:
        agent_id: Agent ID
        agent: Agent object
        from_number: Caller's phone number
        call_sid: Twilio call/message SID
        conversation_type: Type of conversation ("voice" or "message")
        db: Database session

    Returns:
        Created Conversation object
    """
    conversation_service = ConversationService(db)

    session_name = (
        f"{conversation_type.capitalize()} call from {from_number}"
        if conversation_type == "voice"
        else f"SMS from {from_number}"
    )

    conversation = conversation_service.create_conversation(
        agent_id=agent_id,
        caller_phone=from_number,
        conversation_type=conversation_type,
        twilio_sid=call_sid,
        session_name=session_name,
    )

    return conversation


def build_clean_websocket_url(
    base_url: str, agent_id: str, conversation_id: str
) -> str:
    """
    Build a clean WebSocket URL without query parameters that Twilio doesn't handle well.

    Args:
        base_url: Base URL from settings (can include https:// prefix)
        agent_id: Agent ID
        conversation_id: Conversation ID

    Returns:
        Clean WebSocket URL path
    """
    # Remove any protocol prefix from base_url and use wss://
    clean_base = base_url.replace("https://", "").replace("http://", "")
    return f"wss://{clean_base}/agent/ws/{agent_id}/twilio/{conversation_id}/"
