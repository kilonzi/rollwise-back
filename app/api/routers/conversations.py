import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.conversation_schemas import ConversationResponse, MessageResponse
from app.models import get_db, Conversation, Message, Agent
from app.services.audio_service import AudioService
from app.services.conversation_service import ConversationService

router = APIRouter()


def _serialize_conversation(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "agent_id": conv.agent_id,
        "session_name": conv.session_name,
        "conversation_type": conv.conversation_type,
        "caller_phone": conv.caller_phone,
        "twilio_sid": conv.twilio_sid,
        "status": conv.status,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
        "duration_seconds": conv.duration_seconds,
        "summary": conv.summary,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def _serialize_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "content": msg.content,
        "audio_file_path": msg.audio_file_path,
        "sequence_number": msg.sequence_number,
        "message_type": msg.message_type,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
    }


@router.get(
    "/agents/{agent_id}/conversations", response_model=List[ConversationResponse]
)
async def get_agent_conversations(
    agent_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List conversations for a specific agent, ensuring user has access to the agent's tenant."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    service = ConversationService(db)
    conversations = service.get_agent_conversations(
        agent_id, limit=limit, offset=offset
    )
    return conversations


@router.get(
    "/conversations/{conversation_id}/messages", response_model=List[MessageResponse]
)
async def get_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get messages for a conversation, including audio_file_path when available."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.active)
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    conv_service = ConversationService(db)
    messages = conv_service.get_conversation_messages(conversation_id)
    return messages


@router.get("/messages/{message_id}/audio")
async def get_message_audio(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch and stream the audio file for a specific message."""
    message = db.query(Message).filter(Message.id == message_id, Message.active).first()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == message.conversation_id, Conversation.active)
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    audio_path = message.audio_file_path
    if not audio_path:
        # Use predictable path: store/audio/{conversation_id}/{message_id}.wav
        audio_path = AudioService.get_audio_file_path(
            str(conversation.id), str(message.id)
        )
        if os.path.exists(audio_path):
            # Persist the path for future calls
            conv_service = ConversationService(db)
            conv_service.update_message_audio(str(message.id), audio_path)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found for this message",
            )

    if not os.path.exists(audio_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found"
        )

    filename = os.path.basename(audio_path)
    return FileResponse(path=audio_path, media_type="audio/wav", filename=filename)
