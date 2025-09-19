from datetime import datetime
from typing import Dict, Any, List, Optional

import google.generativeai as genai
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.config.agent_functions import FUNCTION_MAP
from app.config.settings import settings
from app.models import Agent, Conversation, Message
from app.services.agent_service import AgentService
from app.services.collection_service import CollectionService
from app.utils.agent_config_builder import AgentConfigBuilder
from app.utils.date_utils import normalize_date_range
from app.utils.logging_config import app_logger


class AgentChatService:
    """Service for agent knowledge querying and conversation analytics with tool calling capabilities."""

    def __init__(self, db: Session):
        self.db = db
        self.collection_service = CollectionService(db)
        self.agent_service = AgentService()

        api_key = settings.GEMINI_API_KEY
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(settings.GEMINI_LLM_MODEL)
        else:
            self.model = None

    async def query_agent_knowledge(
            self,
            agent_id: str,
            query: str,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Query agent's knowledge base and conversation history."""
        try:
            date_from, date_to = normalize_date_range(date_from, date_to)

            agent = self.db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            context_data = self._gather_context_data(agent_id, agent.tenant_id, date_from, date_to)

            # Fetch collection details to pass to the agent
            collection_details = self.collection_service.get_collections_by_agent_id(agent_id)

            if self.model:
                response = await self._generate_ai_response(query, context_data, collection_details, agent)
            else:
                response = "Google Generative AI not configured. Please set the GEMINI_API_KEY environment variable."

            return {
                "success": True,
                "response": response,
                "context_summary": {
                    "conversations_count": len(context_data.get("conversations", [])),
                    "messages_count": len(context_data.get("messages", [])),
                    "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
                },
            }

        except Exception as e:
            app_logger.error(f"Error querying agent knowledge: {e}")
            return {"success": False, "error": str(e)}

    def _gather_context_data(
            self,
            agent_id: str,
            tenant_id: str,
            date_from: datetime,
            date_to: datetime
    ) -> Dict[str, Any]:
        """Gather conversation context within a specified date range."""
        conversations = self.db.query(Conversation).filter(
            and_(
                Conversation.agent_id == agent_id,
                Conversation.tenant_id == tenant_id,
                Conversation.started_at >= date_from,
                Conversation.started_at <= date_to,
                Conversation.active
            )
        ).order_by(desc(Conversation.started_at)).all()

        conversation_ids = [conv.id for conv in conversations]
        messages = []
        if conversation_ids:
            messages = self.db.query(Message).filter(
                Message.conversation_id.in_(conversation_ids),
                Message.active
            ).order_by(Message.sequence_number).all()

        conversation_summaries = [
            {
                "id": conv.id,
                "caller_phone": conv.caller_phone,
                "type": conv.conversation_type,
                "status": conv.status,
                "started_at": conv.started_at.isoformat(),
                "summary": conv.summary or "No summary available",
                "duration_seconds": conv.duration_seconds,
            }
            for conv in conversations
        ]

        message_summaries = [
            {
                "role": msg.role,
                "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages[-50:]
        ]

        return {
            "conversations": conversation_summaries,
            "messages": message_summaries,
            "total_conversations": len(conversations),
            "total_messages": len(messages),
        }

    async def _generate_ai_response(
            self,
            query: str,
            context_data: Dict[str, Any],
            collection_details: List[Dict[str, Any]],
            agent: Agent
    ) -> str:
        """Generate AI response using Google Generative AI with tool calling capabilities."""
        try:
            agent_dict = {
                "id": agent.id,
                "provider": agent.provider,
                "model": agent.model,
            }
            agent_config = self.agent_service.build_agent_config(agent_dict, collection_details)
            system_prompt = agent_config["llm_config"]["system_prompt"]

            context_prompt = self._build_agent_context_prompt(query, context_data, system_prompt)

            function_declarations = self._build_function_declarations(agent.tools)

            if function_declarations:
                model_with_tools = genai.GenerativeModel(
                    model_name=settings.GEMINI_LLM_MODEL,
                    tools=function_declarations
                )
                response = model_with_tools.generate_content(context_prompt)
            else:
                response = self.model.generate_content(context_prompt)

            return await self._process_ai_response(response, agent)

        except Exception as e:
            app_logger.error(f"AI generation error: {e}")
            return f"AI generation error: {str(e)}"

    def _build_agent_context_prompt(
            self,
            query: str,
            context_data: Dict[str, Any],
            system_prompt: str = "",
            collections: list[dict] = None
    ) -> str:
        """
        Build a comprehensive context prompt for the agent, including collection details.
        Args:
            query: The user's query.
            context_data: Conversation and message analytics.
            system_prompt: The base system prompt for the agent.
            collections: List of collection dicts for the agent.
        Returns:
            A formatted prompt string for the LLM.
        """
        prompt = f"{system_prompt}\n\n"
        if collections:
            prompt += AgentConfigBuilder.format_collections_prompt(collections) + "\n"
        prompt += f"CURRENT QUERY: {query}\n\nCONVERSATION ANALYTICS CONTEXT:\n- Total conversations in date range: {context_data['total_conversations']}\n- Total messages in date range: {context_data['total_messages']}\n\nRECENT CONVERSATIONS:\n"
        for conv in context_data['conversations'][:10]:
            prompt += f"- Call from {conv['caller_phone']} on {conv['started_at']}: {conv['summary']}\n"
        prompt += "\nRECENT MESSAGES:\n"
        for msg in context_data['messages'][-20:]:
            prompt += f"- {msg['role']}: {msg['content']}\n"
        prompt += "\nInstructions:\n- Always respond in Markdown format.\n- Be concise and to the point.\n- Use the context provided to inform your response.\n- If you need to use tools, call them with the proper parameters.\n- If no relevant data exists, state that clearly.\n\nAnswer:\n"
        return prompt

    def _build_function_declarations(self, agent_tools: List[str]) -> List[Dict[str, Any]]:
        """Build function declarations for Google Generative AI function calling."""
        tool_schemas = {
            "search_collection": {
                "name": "search_collection",
                "description": "Searches a specific collection for relevant information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "collection_name": {
                            "type": "string",
                            "description": "The name of the collection to search.",
                        },
                        "query": {
                            "type": "string",
                            "description": "The user's query to search for.",
                        },
                        "k": {
                            "type": "integer",
                            "description": "The number of results to return.",
                            "default": 10,
                        }
                    },
                    "required": ["collection_name", "query"],
                },
            }
            # Add other tool schemas here if needed
        }

        return [tool_schemas[tool] for tool in agent_tools if tool in tool_schemas]

    async def _process_ai_response(self, response, agent: Agent) -> str:
        """Process AI response and execute any function calls."""
        try:
            response_text = ""
            if not (hasattr(response, 'candidates') and response.candidates):
                return response.text if hasattr(response, 'text') else "Unable to generate response."

            candidate = response.candidates[0]
            if not (hasattr(candidate, 'content') and candidate.content.parts):
                return "No content in response candidate."

            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    response_text += part.text
                elif hasattr(part, 'function_call'):
                    function_call = part.function_call
                    tool_result = await self._execute_tool(
                        function_call.name, dict(function_call.args), agent
                    )
                    result_str = tool_result.get('data') or tool_result.get('message', 'No result.')
                    status = "success" if tool_result.get('success') else "error"
                    response_text += f"\n\n[Tool call: {function_call.name}, Status: {status}]\nResult: {result_str}\n"

            return response_text or "Unable to generate a valid response."

        except Exception as e:
            app_logger.error(f"Error processing AI response: {e}")
            return f"Error processing response: {str(e)}"

    async def _execute_tool(self, tool_name: str, tool_params: Dict[str, Any], agent: Agent) -> Dict[str, Any]:
        """Execute a specific tool with given parameters."""
        try:
            if tool_name not in FUNCTION_MAP:
                return {"success": False, "error": f"Tool '{tool_name}' not found."}

            tool_params.update({"agent_id": agent.id, "tenant_id": agent.tenant_id})
            tool_function = FUNCTION_MAP[tool_name]
            result = await tool_function(**tool_params)

            app_logger.info(f"Executed tool '{tool_name}' for agent {agent.id}: Success={result.get('success', False)}")
            return result

        except Exception as e:
            app_logger.error(f"Error executing tool '{tool_name}': {e}")
            return {"success": False, "error": str(e)}
