from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Conversation, Message, Agent
from app.utils.logging_config import app_logger as logger
from app.utils.vertex_ai_client import get_vertex_ai_client


class ConversationService:
    """Service for managing conversations, messages, and summaries"""

    def __init__(self, db: Session):
        self.db = db
        # Initialize Vertex AI client
        vertex_client = get_vertex_ai_client()
        self.model = vertex_client.get_model()

    def create_conversation(
            self,
            agent_id: str,
            caller_phone: str,
            conversation_type: str,
            session_name: str,
            twilio_sid: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation and automatically create a preemptive order"""
        conversation = Conversation(
            agent_id=agent_id,
            caller_phone=caller_phone,
            conversation_type=conversation_type,
            session_name=session_name,
            twilio_sid=twilio_sid,
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        # Automatically create a preemptive order for this conversation
        self._create_preemptive_order(conversation)

        return conversation

    def _create_preemptive_order(self, conversation: Conversation) -> None:
        """Create a preemptive order when a conversation starts"""
        try:
            from app.models import Order
            preemptive_order = Order(
                agent_id=conversation.agent_id,
                conversation_id=conversation.id,
                customer_phone=conversation.caller_phone,
                customer_name="",
                status="new",
                total_price=0.0,
                active=False
            )
            self.db.add(preemptive_order)
            self.db.commit()

            logger.info(f"Created preemptive order for conversation {conversation.id}")

        except Exception as e:
            # Don't fail the conversation creation if order creation fails
            logger.error(f"Failed to create preemptive order for conversation {conversation.id}: {str(e)}")
            # Rollback any partial order creation, but keep the conversation
            self.db.rollback()
            # Re-commit the conversation
            self.db.commit()

    def end_conversation(self, conversation_id: str) -> bool:
        """End a conversation and calculate duration"""
        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            return False
        conversation.ended_at = datetime.now()
        conversation.status = "completed"
        if conversation.started_at:
            duration = (conversation.ended_at - conversation.started_at).total_seconds()
            conversation.duration_seconds = str(int(duration))
        self.db.commit()
        return True

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID"""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.active).first()

    def add_message(
            self,
            conversation_id: str,
            role: str,
            content: str,
            audio_file_path: Optional[str] = None,
            message_type: str = "conversation"
    ) -> Message:
        """Add a new message to a conversation."""
        max_seq = self.db.query(func.max(Message.sequence_number)).filter(
            Message.conversation_id == conversation_id).scalar() or 0
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
        logger.info("Added message #%s: %s -> %s...", message.sequence_number, role, content[:100])
        return message

    def get_conversation_messages(self, conversation_id: str) -> List[Message]:
        """Get all messages for a conversation."""
        return self.db.query(Message).filter(Message.conversation_id == conversation_id, Message.active).order_by(
            Message.sequence_number).all()

    def update_message_audio(self, message_id: str, audio_file_path: str) -> Optional[Message]:
        """Update a message with the path to its audio file."""
        message = self.db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.audio_file_path = audio_file_path
            self.db.commit()
            logger.info("Updated message %s with audio: %s", message_id, audio_file_path)
        return message

    async def summarize_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Generate a comprehensive summary of the conversation."""
        if not self.model:
            logger.warning("Summarization service not available. Vertex AI client not initialized.")
            return None

        messages = self.get_messages_for_summary(conversation_id)
        if not messages:
            logger.info("No messages found for conversation %s", conversation_id)
            return None

        conversation_text = self._format_messages_for_llm(messages)
        try:
            full_prompt = f"{self._get_summarization_prompt()}\n\nConversation to summarize:\n\n{conversation_text}"
            summary_response = self.model.generate_content(full_prompt)
            summary = summary_response.text
            summary_data = {
                "conversation_id": conversation_id,
                "summary": summary,
                "message_count": len(messages),
                "participants": self._extract_participants(messages),
                "key_topics": self._extract_key_topics(messages),
                "duration_estimate": self._estimate_duration(messages),
                "generated_at": messages[-1]["timestamp"] if messages else None
            }
            logger.info("Generated summary for conversation %s: %d chars", conversation_id, len(summary))
            await self.store_summary_in_conversation(conversation_id, summary_data)
            return summary_data
        except Exception as e:
            logger.exception("Error generating summary for conversation %s: %s", conversation_id, str(e))
            return {"conversation_id": conversation_id, "summary": "Summary generation failed", "error": str(e),
                    "message_count": len(messages)}

    def get_messages_for_summary(self, conversation_id: str) -> List[dict]:
        """Get messages formatted for LLM summarization"""
        messages = self.get_conversation_messages(conversation_id)
        return [{"role": msg.role, "content": msg.content, "timestamp": msg.created_at.isoformat(),
                 "sequence": msg.sequence_number} for msg in messages if msg.message_type == "conversation"]

    def _format_messages_for_llm(self, messages: List[Dict]) -> str:
        """Format messages for LLM processing"""
        return "\n".join([f"[{msg['sequence']:03d}] {msg['role'].upper()}: {msg['content']}" for msg in messages])

    def _get_summarization_prompt(self) -> str:
        """Get the system prompt for conversation summarization"""
        return """You are an expert conversation summarizer for business phone calls.

Analyze the conversation and provide a summary in the following exact format:

**KEY POINTS:**
• Customer's primary need or request
• Main services/information discussed
• Any searches performed (clients, pricing, hours, inventory)
• Specific results or data provided
• Actions taken or next steps
• Call outcome

**DETAILED SUMMARY:**

Provide a comprehensive narrative summary of the entire conversation. Include:
- Why the customer called and their specific needs
- How the business agent responded and what information was shared
- Any function calls made (searches for clients, pricing, hours, inventory, etc.) and their results
- The overall tone and satisfaction level of the interaction
- Any follow-up actions mentioned or required
- Business insights or customer service quality observations

Keep the summary professional, detailed, and focused on business-relevant information that would be valuable for customer service review and business intelligence."""

    def _extract_participants(self, messages: List[Dict]) -> List[str]:
        """Extract unique participants from messages"""
        return list(set(msg["role"] for msg in messages if msg["role"] not in ["system"]))

    def _extract_key_topics(self, messages: List[Dict]) -> List[str]:
        """Extract key topics mentioned in the conversation"""
        keywords = set()
        common_business_terms = ["appointment", "booking", "price", "cost", "hours", "schedule", "service", "client",
                                 "customer", "inventory", "product", "meeting"]
        for msg in messages:
            content_lower = msg["content"].lower()
            for term in common_business_terms:
                if term in content_lower:
                    keywords.add(term)
        return list(keywords)

    def _estimate_duration(self, messages: List[Dict]) -> str:
        """Estimate conversation duration based on message count and content"""
        if len(messages) < 5:
            return "< 2 minutes"
        elif len(messages) < 15:
            return "2-5 minutes"
        elif len(messages) < 30:
            return "5-10 minutes"
        else:
            return "> 10 minutes"

    async def store_summary_in_conversation(self, conversation_id: str, summary_data: Dict[str, Any]):
        """Store the generated summary directly in the conversation table"""
        if not summary_data or summary_data.get('error'):
            logger.warning("No valid summary to store for conversation %s", conversation_id)
            return False
        try:
            summary_text = summary_data.get('summary', 'No summary available')
            success = self.update_conversation_summary(conversation_id=conversation_id, summary=summary_text)
            if success:
                logger.info("Stored conversation summary in database for %s", conversation_id)
            else:
                logger.error("Failed to store summary for %s", conversation_id)
            return success
        except Exception as e:
            logger.exception("Error storing summary for conversation %s: %s", conversation_id, str(e))
            return False

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

    def get_agent_conversations(
            self, agent_id: str, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        """Get conversations for an agent"""
        return (
            self.db.query(Conversation)
            .join(Agent)
            .filter(
                Conversation.agent_id == agent_id,
                Conversation.active,
                Agent.active,
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_caller_conversations(
            self, caller_phone: str, agent_id: str = None, limit: int = 10
    ) -> List[Conversation]:
        """Get conversation history for a specific caller"""
        query = (
            self.db.query(Conversation)
            .join(Agent)
            .filter(
                Conversation.caller_phone == caller_phone,
                Conversation.active,
                Agent.active,
            )
        )

        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)

        return query.order_by(Conversation.created_at.desc()).limit(limit).all()
