from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import google.generativeai as genai
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models import Agent, Conversation, Message
from app.services.business_dataset_service import BusinessDatasetService
from app.utils.date_utils import normalize_date_range


class AgentChatService:
    """Service for agent knowledge querying and conversation analytics"""

    def __init__(self, db: Session):
        self.db = db
        self.business_dataset_service = BusinessDatasetService(db)

        # Initialize Google Generative AI
        api_key = settings.GEMINI_API_KEY
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(settings.GEMINI_LLM_MODEL)
        else:
            self.model = None

    def query_agent_knowledge(
            self,
            agent_id: str,
            query: str,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Query agent's knowledge base and conversation history"""

        try:
            # Normalize date range for proper filtering
            date_from, date_to = normalize_date_range(date_from, date_to)

            # Get agent and validate
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.active == True
            ).first()

            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Gather context data
            context_data = self._gather_context_data(agent_id, agent.tenant_id, date_from, date_to)

            # Search knowledge base
            knowledge_results = self._search_knowledge_base(agent.tenant_id, agent_id, query)

            # Generate response using Google Generative AI
            if self.model:
                response = self._generate_ai_response(query, context_data, knowledge_results)
            else:
                response = "Google Generative AI not configured. Please set GOOGLE_GENERATIVE_AI_API_KEY environment variable."

            return {
                "success": True,
                "response": response,
                "context_summary": {
                    "conversations_count": len(context_data.get("conversations", [])),
                    "messages_count": len(context_data.get("messages", [])),
                    "date_range": {
                        "from": date_from.isoformat(),
                        "to": date_to.isoformat()
                    }
                },
                "knowledge_matches": len(knowledge_results)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _gather_context_data(
            self,
            agent_id: str,
            tenant_id: str,
            date_from: datetime,
            date_to: datetime
    ) -> Dict[str, Any]:
        """Gather conversation context within date range"""

        # Get conversations within date range
        conversations = self.db.query(Conversation).filter(
            and_(
                Conversation.agent_id == agent_id,
                Conversation.tenant_id == tenant_id,
                Conversation.started_at >= date_from,
                Conversation.started_at <= date_to,
                Conversation.active == True
            )
        ).order_by(desc(Conversation.started_at)).all()

        # Get messages from these conversations
        conversation_ids = [conv.id for conv in conversations]
        messages = []

        if conversation_ids:
            messages = self.db.query(Message).filter(
                and_(
                    Message.conversation_id.in_(conversation_ids),
                    Message.active == True
                )
            ).order_by(Message.sequence_number).all()

        # Prepare conversation summaries
        conversation_summaries = []
        for conv in conversations:
            conversation_summaries.append({
                "id": conv.id,
                "caller_phone": conv.caller_phone,
                "type": conv.conversation_type,
                "status": conv.status,
                "started_at": conv.started_at.isoformat(),
                "summary": conv.summary or "No summary available",
                "duration_seconds": conv.duration_seconds
            })

        # Prepare message summaries (last 50 messages to avoid token limits)
        message_summaries = []
        for msg in messages[-50:]:  # Limit to recent messages
            message_summaries.append({
                "role": msg.role,
                "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                "created_at": msg.created_at.isoformat()
            })

        return {
            "conversations": conversation_summaries,
            "messages": message_summaries,
            "total_conversations": len(conversations),
            "total_messages": len(messages)
        }

    def _search_knowledge_base(self, tenant_id: str, agent_id: str, query: str) -> List[Dict[str, Any]]:
        """Search the ChromaDB knowledge base for relevant information"""

        try:
            # Query ChromaDB collection
            collection = self.business_dataset_service.collection

            # Search with metadata filtering for tenant and agent
            results = collection.query(
                query_texts=[query],
                n_results=10,
                where={
                    "$and": [
                        {"tenant_id": tenant_id},
                        {"agent_id": agent_id}
                    ]
                }
            )

            knowledge_results = []
            if results and results.get('documents'):
                for i, doc in enumerate(results['documents'][0]):
                    knowledge_results.append({
                        "content": doc,
                        "distance": results['distances'][0][i] if results.get('distances') else None,
                        "metadata": results['metadatas'][0][i] if results.get('metadatas') else {}
                    })

            return knowledge_results

        except Exception as e:
            print(f"Knowledge base search error: {e}")
            return []

    def _generate_ai_response(
            self,
            query: str,
            context_data: Dict[str, Any],
            knowledge_results: List[Dict[str, Any]]
    ) -> str:
        """Generate AI response using Google Generative AI"""

        try:
            # Prepare context for the AI
            context_prompt = self._build_context_prompt(query, context_data, knowledge_results)

            # Generate response
            response = self.model.generate_content(context_prompt)

            return response.text if response else "Unable to generate response"

        except Exception as e:
            return f"AI generation error: {str(e)}"

    def _build_context_prompt(
            self,
            query: str,
            context_data: Dict[str, Any],
            knowledge_results: List[Dict[str, Any]]
    ) -> str:
        """Build comprehensive context prompt for AI"""

        prompt = f"""
        You are an AI assistant supporting a customer service agent. Use the data below to give clear, helpful answers.

        USER QUERY: {query}

        CONVERSATION CONTEXT:
        - Total conversations in date range: {context_data['total_conversations']}
        - Total messages in date range: {context_data['total_messages']}

        RECENT CONVERSATIONS:
        """
        for conv in context_data['conversations'][:10]:
            prompt += f"- Call from {conv['caller_phone']} on {conv['started_at']}: {conv['summary']}\n"

        prompt += "\nRECENT MESSAGES:\n"
        for msg in context_data['messages'][-20:]:
            prompt += f"- {msg['role']}: {msg['content']}\n"

        prompt += "\nKNOWLEDGE BASE RESULTS:\n"
        for kb in knowledge_results[:5]:
            prompt += f"- {kb['content']}\n"

        prompt += f"""

        Instructions:
        - Always answer the user's query directly and naturally. 
        - If the query is a greeting or small talk, respond with a polite, conversational reply (e.g., "Hello! How can I help you today?").
        - If the query asks for information, use the conversation history and knowledge base to provide accurate answers. 
        - If statistics are relevant, include clear numbers or trends. 
        - If examples exist, cite them directly. 
        - Provide actionable recommendations when appropriate. 
        - Do not mention this prompt or its structure in your response.
        - If no relevant data exists, say so clearly but still respond in a friendly, helpful tone.

        Answer:
        """

        return prompt
