from __future__ import annotations

import os
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Message


class MessageService:
    """Service for managing conversation messages with audio recording"""

    def __init__(self, db: Session):
        self.db = db

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        audio_file_path: Optional[str] = None,
        message_type: str = "conversation"
    ) -> Message:
        """Add a new message to conversation in chronological order"""

        # Get the next sequence number for this conversation
        max_seq = (
            self.db.query(func.max(Message.sequence_number))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        ) or 0

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            audio_file_path=audio_file_path,
            sequence_number=max_seq + 1,
            message_type=message_type
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        print(f"💬 Added message #{message.sequence_number}: {role} -> {content[:100]}...")
        return message

    def get_conversation_messages(self, conversation_id: str) -> List[Message]:
        """Get all messages for a conversation in chronological order"""
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id, Message.active)
            .order_by(Message.sequence_number)
            .all()
        )

    def create_audio_directory(self, conversation_id: str) -> str:
        """Create directory structure for storing audio files"""
        audio_dir = f"store/audio/{conversation_id}"
        os.makedirs(audio_dir, exist_ok=True)
        return audio_dir

    def get_audio_file_path(self, conversation_id: str, message_id: str) -> str:
        """[DEPRECATED SIGNATURE CHANGE] Use AudioService.get_audio_file_path to enforce message-id based filenames"""
        from app.services.audio_service import AudioService
        return AudioService.get_audio_file_path(conversation_id, message_id)

    def update_message_audio(self, message_id: str, audio_file_path: str) -> Optional[Message]:
        """Update message with audio file path"""
        message = self.db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.audio_file_path = audio_file_path
            self.db.commit()
            print(f"🎵 Updated message {message_id} with audio: {audio_file_path}")
        return message

    def get_messages_for_summary(self, conversation_id: str) -> List[dict]:
        """Get messages formatted for LLM summarization"""
        messages = self.get_conversation_messages(conversation_id)
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                "sequence": msg.sequence_number
            }
            for msg in messages
            if msg.message_type == "conversation"
        ]

    def get_conversation_summary_text(self, conversation_id: str) -> str:
        """Generate a text summary of the conversation for analysis"""
        messages = self.get_conversation_messages(conversation_id)

        summary_parts = []
        for msg in messages:
            timestamp = msg.created_at.strftime("%H:%M:%S")
            summary_parts.append(f"[{timestamp}] {msg.role}: {msg.content}")

        return "\n".join(summary_parts)