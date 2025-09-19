from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from app.models import Conversation, Message, Agent, Tenant
from app.utils.logging_config import app_logger as logger


class ConversationService:
    """Service for managing conversations and transcripts"""

    def __init__(self, db: Session):
        self.db = db

    def create_conversation(
        self,
        agent_id: str,
        tenant_id: str,
        caller_phone: str,
        conversation_type: str,
        session_name: str,
        twilio_sid: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation"""

        conversation = Conversation(
            agent_id=agent_id,
            tenant_id=tenant_id,
            caller_phone=caller_phone,
            conversation_type=conversation_type,
            session_name=session_name,
            twilio_sid=twilio_sid,
            status="active",
        )

        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        # No need to create empty transcript anymore - messages are created as needed

        return conversation

    def end_conversation(self, conversation_id: str) -> bool:
        """End a conversation and calculate duration"""

        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if not conversation:
            return False

        # Update conversation status
        conversation.ended_at = datetime.now()
        conversation.status = "completed"

        # Calculate duration if we have start time
        if conversation.started_at:
            duration = (conversation.ended_at - conversation.started_at).total_seconds()
            conversation.duration_seconds = str(int(duration))

        self.db.commit()
        return True

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID"""
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.active)
            .first()
        )

    def add_message(
        self, conversation_id: str, role: str, content: str, audio_file_path: Optional[str] = None
    ) -> bool:
        """Add a message to conversation - DEPRECATED: Use MessageService instead"""
        from app.services.message_service import MessageService

        message_service = MessageService(self.db)
        message_service.add_message(conversation_id, role, content, audio_file_path)
        return True

    def get_conversation_messages(self, conversation_id: str) -> List[Message]:
        """Get all messages for a conversation"""
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id, Message.active)
            .order_by(Message.sequence_number)
            .all()
        )

    def update_conversation_summary(self, conversation_id: str, summary: str) -> bool:
        """Update conversation with AI-generated summary"""
        try:
            conversation = (
                self.db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.active)
                .first()
            )

            if conversation:
                conversation.summary = summary
                conversation.updated_at = datetime.now()
                self.db.commit()
                logger.info("Updated conversation %s with summary", conversation_id)
                return True
            else:
                logger.warning("Conversation %s not found for summary update", conversation_id)
                return False

        except Exception as e:
            logger.exception("Error updating conversation summary: %s", str(e))
            self.db.rollback()
            return False

    def get_tenant_conversations(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        """Get conversations for a tenant (only active conversations and tenants)"""
        return (
            self.db.query(Conversation)
            .join(Tenant)
            .filter(
                Conversation.tenant_id == tenant_id,
                Conversation.active,
                Tenant.active,
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_agent_conversations(
        self, agent_id: str, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        """Get conversations for an agent (only active conversations, agents, and tenants)"""
        return (
            self.db.query(Conversation)
            .join(Agent)
            .join(Tenant)
            .filter(
                Conversation.agent_id == agent_id,
                Conversation.active,
                Agent.active,
                Tenant.active,
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_caller_conversations(
        self, caller_phone: str, agent_id: str = None, limit: int = 10
    ) -> List[Conversation]:
        """Get conversation history for a specific caller (only active conversations, agents, and tenants)"""
        query = (
            self.db.query(Conversation)
            .join(Agent)
            .join(Tenant)
            .filter(
                Conversation.caller_phone == caller_phone,
                Conversation.active,
                Agent.active,
                Tenant.active,
            )
        )

        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)

        return query.order_by(Conversation.created_at.desc()).limit(limit).all()
