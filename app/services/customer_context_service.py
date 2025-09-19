"""
Customer Context Service

Retrieves customer history and context from previous conversations
to provide personalized service during calls.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from app.models import Conversation, Agent
from app.services.conversation_service import ConversationService
from app.utils.logging_config import app_logger as logger


class CustomerContextService:
    """
    Service for retrieving and building customer context from conversation history.

    Provides insights about customer's previous interactions, preferences,
    and conversation patterns to enhance personalized service.
    """

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.conversation_service = ConversationService(db_session)

    async def get_customer_context(
        self,
        phone_number: str,
        agent_id: str,
        lookback_days: int = 90,
        max_conversations: int = 10
    ) -> Dict[str, Any]:
        """
        Get comprehensive customer context from previous conversations.

        Args:
            phone_number: Customer's phone number
            agent_id: Current agent ID
            lookback_days: How many days back to search
            max_conversations: Maximum number of conversations to analyze

        Returns:
            Dict containing customer context information
        """
        try:
            # Get agent info for tenant context
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return self._empty_context("Agent not found")

            # Calculate date range
            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            # Get previous conversations for this phone number and tenant
            previous_conversations = (
                self.db_session.query(Conversation)
                .filter(
                    and_(
                        Conversation.caller_phone == phone_number,
                        Conversation.tenant_id == agent.tenant_id,
                        Conversation.created_at >= cutoff_date,
                        Conversation.summary.isnot(None),  # Only conversations with summaries
                        Conversation.summary != ""
                    )
                )
                .order_by(desc(Conversation.created_at))
                .limit(max_conversations)
                .all()
            )

            if not previous_conversations:
                return self._empty_context("No previous conversations found")

            # Build customer context
            context = await self._build_customer_context(
                previous_conversations,
                phone_number,
                agent.tenant_id
            )

            return context

        except Exception as e:
            logger.exception("Error getting customer context: %s", str(e))
            return self._empty_context(f"Error: {str(e)}")

    async def _build_customer_context(
        self,
        conversations: List[Conversation],
        phone_number: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Build comprehensive customer context from conversation history."""

        # Extract summaries and metadata
        summaries = []
        total_calls = len(conversations)
        conversation_types = {}
        recent_topics = []
        customer_preferences = []

        for conv in conversations:
            # Parse summary (assuming it's JSON or structured text)
            summary_data = self._parse_summary(conv.summary)

            summaries.append({
                "date": conv.created_at.strftime("%Y-%m-%d"),
                "type": conv.conversation_type,
                "summary": summary_data.get("summary", conv.summary),
                "key_points": summary_data.get("key_points", []),
                "sentiment": summary_data.get("sentiment", "neutral"),
                "topics": summary_data.get("topics", []),
                "outcome": summary_data.get("outcome", "completed"),
                "duration_minutes": self._calculate_duration(conv)
            })

            # Track conversation types
            conv_type = conv.conversation_type
            conversation_types[conv_type] = conversation_types.get(conv_type, 0) + 1

            # Collect topics from recent conversations (last 5)
            if len(recent_topics) < 15:  # Limit recent topics
                topics = summary_data.get("topics", [])
                recent_topics.extend(topics)

            # Extract preferences
            preferences = summary_data.get("preferences", [])
            customer_preferences.extend(preferences)

        # Get most recent conversation for quick reference
        latest_conversation = summaries[0] if summaries else None

        # Calculate customer insights
        interaction_frequency = self._calculate_interaction_frequency(conversations)
        preferred_contact_type = max(conversation_types.items(), key=lambda x: x[1])[0] if conversation_types else "voice"

        # Build context prompt
        context_summary = self._build_context_summary(
            phone_number=phone_number,
            total_calls=total_calls,
            latest_conversation=latest_conversation,
            recent_topics=list(set(recent_topics[:10])),  # Unique recent topics
            preferred_contact=preferred_contact_type,
            interaction_frequency=interaction_frequency,
            customer_preferences=list(set(customer_preferences[:5]))  # Unique preferences
        )

        return {
            "has_history": True,
            "phone_number": phone_number,
            "total_previous_calls": total_calls,
            "conversation_types": conversation_types,
            "latest_conversation_date": conversations[0].created_at.strftime("%Y-%m-%d %H:%M"),
            "interaction_frequency": interaction_frequency,
            "preferred_contact_type": preferred_contact_type,
            "recent_topics": list(set(recent_topics[:10])),
            "customer_preferences": list(set(customer_preferences[:5])),
            "context_summary": context_summary,
            "detailed_summaries": summaries[:5],  # Last 5 detailed summaries
            "lookback_period": f"Last {len(conversations)} conversations"
        }

    def _parse_summary(self, summary: str) -> Dict[str, Any]:
        """Parse conversation summary (JSON or plain text)."""
        try:
            import json
            # Try to parse as JSON first
            if summary.strip().startswith('{'):
                return json.loads(summary)
        except Exception:
            pass

        # Fallback to plain text parsing
        return {
            "summary": summary,
            "key_points": [],
            "sentiment": "neutral",
            "topics": [],
            "outcome": "completed",
            "preferences": []
        }

    def _calculate_duration(self, conversation: Conversation) -> Optional[int]:
        """Calculate conversation duration in minutes."""
        if conversation.ended_at and conversation.created_at:
            delta = conversation.ended_at - conversation.created_at
            return int(delta.total_seconds() / 60)
        return None

    def _calculate_interaction_frequency(self, conversations: List[Conversation]) -> str:
        """Calculate how frequently customer contacts."""
        if len(conversations) < 2:
            return "new_customer"

        # Calculate average days between conversations
        total_days = (conversations[0].created_at - conversations[-1].created_at).days
        avg_days_between = total_days / (len(conversations) - 1) if len(conversations) > 1 else 0

        if avg_days_between <= 7:
            return "frequent"  # Weekly or more
        elif avg_days_between <= 30:
            return "regular"   # Monthly
        else:
            return "occasional"  # Less than monthly

    def _build_context_summary(
        self,
        phone_number: str,
        total_calls: int,
        latest_conversation: Optional[Dict],
        recent_topics: List[str],
        preferred_contact: str,
        interaction_frequency: str,
        customer_preferences: List[str]
    ) -> str:
        """Build a concise context summary for the agent prompt."""

        context_parts = []

        # Customer identification
        context_parts.append(f"RETURNING CUSTOMER: {phone_number}")

        # Interaction history
        frequency_desc = {
            "frequent": "calls frequently (weekly or more)",
            "regular": "calls regularly (monthly)",
            "occasional": "calls occasionally",
            "new_customer": "new customer"
        }
        context_parts.append(f"History: {total_calls} previous conversations, {frequency_desc.get(interaction_frequency, 'unknown pattern')}")

        # Latest interaction
        if latest_conversation:
            days_ago = (datetime.now() - datetime.strptime(latest_conversation["date"], "%Y-%m-%d")).days
            if days_ago == 0:
                time_desc = "earlier today"
            elif days_ago == 1:
                time_desc = "yesterday"
            elif days_ago <= 7:
                time_desc = f"{days_ago} days ago"
            else:
                time_desc = f"on {latest_conversation['date']}"

            context_parts.append(f"Last contact: {time_desc} - {latest_conversation.get('summary', 'No summary')[:100]}")

        # Recent topics
        if recent_topics:
            topics_str = ", ".join(recent_topics[:5])
            context_parts.append(f"Recent topics: {topics_str}")

        # Preferences
        if customer_preferences:
            prefs_str = ", ".join(customer_preferences[:3])
            context_parts.append(f"Preferences: {prefs_str}")

        # Contact preference
        if preferred_contact != "voice":
            context_parts.append(f"Usually contacts via: {preferred_contact}")

        return " | ".join(context_parts)

    def _empty_context(self, reason: str) -> Dict[str, Any]:
        """Return empty context structure."""
        return {
            "has_history": False,
            "phone_number": "",
            "total_previous_calls": 0,
            "context_summary": "NEW CUSTOMER: No previous interaction history",
            "reason": reason,
            "detailed_summaries": [],
            "recent_topics": [],
            "customer_preferences": [],
            "lookback_period": "N/A"
        }

    async def get_customer_quick_context(self, phone_number: str, agent_id: str) -> str:
        """
        Get a quick one-line customer context for immediate use.

        Returns:
            Quick context string for agent awareness
        """
        context = await self.get_customer_context(phone_number, agent_id, lookback_days=30, max_conversations=3)
        return context["context_summary"]

    async def update_customer_preferences(
        self,
        phone_number: str,
        agent_id: str,
        preferences: List[str]
    ) -> bool:
        """
        Update customer preferences based on current conversation.

        This can be called during or after conversations to track preferences.
        """
        try:
            # Implementation would store preferences in a customer profile table
            # For now, we'll log them for future implementation
            logger.info("Customer preferences update for %s: %s", phone_number, preferences)
            return True
        except Exception as e:
            logger.exception("Error updating customer preferences: %s", str(e))
            return False