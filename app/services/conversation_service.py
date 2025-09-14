from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from app.models import Conversation, Transcript, Agent, Tenant


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

        # Create empty transcript
        transcript = Transcript(conversation_id=conversation.id, content="")
        self.db.add(transcript)
        self.db.commit()

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

    def add_to_transcript(
        self, conversation_id: str, speaker: str, content: str
    ) -> bool:
        """Add content to conversation transcript"""

        # Get existing transcript
        transcript = (
            self.db.query(Transcript)
            .filter(Transcript.conversation_id == conversation_id)
            .first()
        )

        if not transcript:
            # Create new transcript if none exists
            transcript = Transcript(conversation_id=conversation_id, content="")
            self.db.add(transcript)

        # Format the new content with timestamp and speaker
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_line = f"[{timestamp}] {speaker.upper()}: {content}\n"

        # Append to existing content
        transcript.content = (transcript.content or "") + new_line
        transcript.updated_at = datetime.now()

        self.db.commit()
        return True

    def get_transcript_content(self, conversation_id: str) -> Optional[str]:
        """Get the full transcript content for a conversation"""
        transcript = (
            self.db.query(Transcript)
            .filter(Transcript.conversation_id == conversation_id)
            .first()
        )

        return transcript.content if transcript else None

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
