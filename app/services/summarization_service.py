from __future__ import annotations

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import google.generativeai as genai
import os

# Models are imported within functions to avoid circular imports
from app.services.message_service import MessageService


class SummarizationService:
    """Service for generating conversation summaries using LLM"""

    def __init__(self, db: Session):
        self.db = db
        # Initialize Google Gemini AI
        genai.configure(api_key=os.getenv("GOOGLE_AI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def summarize_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Generate a comprehensive summary of the conversation"""

        message_service = MessageService(self.db)
        messages = message_service.get_messages_for_summary(conversation_id)

        if not messages:
            print(f"📝 No messages found for conversation {conversation_id}")
            return None

        # Format messages for LLM
        conversation_text = self._format_messages_for_llm(messages)

        try:
            # Create the full prompt with system instructions and conversation
            full_prompt = f"{self._get_summarization_prompt()}\n\nConversation to summarize:\n\n{conversation_text}"

            # Generate summary using Google Gemini
            summary_response = self.model.generate_content(full_prompt)
            summary = summary_response.text

            # Create structured summary
            summary_data = {
                "conversation_id": conversation_id,
                "summary": summary,
                "message_count": len(messages),
                "participants": self._extract_participants(messages),
                "key_topics": self._extract_key_topics(messages),
                "duration_estimate": self._estimate_duration(messages),
                "generated_at": messages[-1]["timestamp"] if messages else None
            }

            print(f"📝 Generated summary for conversation {conversation_id}: {len(summary)} chars")
            return summary_data

        except Exception as e:
            print(f"❌ Error generating summary: {str(e)}")
            return {
                "conversation_id": conversation_id,
                "summary": "Summary generation failed",
                "error": str(e),
                "message_count": len(messages)
            }

    def _format_messages_for_llm(self, messages: List[Dict]) -> str:
        """Format messages for LLM processing"""
        formatted_lines = []

        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            sequence = msg["sequence"]
            formatted_lines.append(f"[{sequence:03d}] {role}: {content}")

        return "\n".join(formatted_lines)

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
        participants = set()
        for msg in messages:
            if msg["role"] not in ["system"]:
                participants.add(msg["role"])
        return list(participants)

    def _extract_key_topics(self, messages: List[Dict]) -> List[str]:
        """Extract key topics mentioned in the conversation"""
        # Simple keyword extraction - could be enhanced with NLP
        keywords = set()
        common_business_terms = [
            "appointment", "booking", "price", "cost", "hours", "schedule",
            "service", "client", "customer", "inventory", "product", "meeting"
        ]

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
        from app.services.conversation_service import ConversationService

        if not summary_data or summary_data.get('error'):
            print(f"⚠️ No valid summary to store for conversation {conversation_id}")
            return False

        try:
            conversation_service = ConversationService(self.db)

            # Store just the summary text in the conversation table
            summary_text = summary_data.get('summary', 'No summary available')

            success = conversation_service.update_conversation_summary(
                conversation_id=conversation_id,
                summary=summary_text
            )

            if success:
                print(f"✅ Stored conversation summary in database for {conversation_id}")
            else:
                print(f"❌ Failed to store summary for {conversation_id}")

            return success

        except Exception as e:
            print(f"❌ Error storing summary: {str(e)}")
            return False