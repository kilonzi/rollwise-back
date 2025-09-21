from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session
from vertexai.generative_models import FunctionDeclaration, Tool

from app.config.agent_functions import FUNCTION_MAP
from app.models import Agent, Conversation, Message, Collection
from app.services.collection_service import CollectionService
from app.utils.agent_config_builder import AgentConfigBuilder
from app.utils.date_utils import normalize_date_range
# from app.services.calendar_service import CalendarService
from app.utils.logging_config import app_logger
from app.utils.vertex_ai_client import get_vertex_ai_client


class AgentService:
    """Service for managing AI agents and their configurations"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.collection_service = CollectionService(db_session)
        vertex_client = get_vertex_ai_client()
        self.model = vertex_client.get_model()

    def build_agent_config(self, agent: Agent, customer_context: str = "", dataset_details: str = "",
                           collection_details: str = "") -> Dict[str, Any]:
        """Build Deepgram agent configuration from database agent record with comprehensive context"""
        try:
            # Use the AgentConfigBuilder to build the configuration with comprehensive context
            return AgentConfigBuilder.build_agent_config(
                agent,
                customer_context=customer_context,
                collection_details=collection_details
            )
        except Exception as e:
            app_logger.error(f"Failed to build agent config for agent {agent.id}: {str(e)}")
            # Return a minimal fallback configuration to prevent call drops
            return {
                "agent": {
                    "speak": {
                        "provider": {
                            "model": agent.voice_model or "aura-2-thalia-en"
                        }
                    },
                    "language": agent.language or "en",
                    "think": {
                        "prompt": agent.system_prompt or "You are a helpful AI assistant.",
                        "functions": []
                    },
                    "greeting": agent.greeting or "Hello! How can I help you today?"
                }
            }

    def get_agent_by_phone(self, phone_number: str) -> Optional[Agent]:
        """Get agent by phone number"""
        return (
            self.db_session.query(Agent)
            .filter(
                Agent.phone_number == phone_number,
                Agent.active,
            )
            .first()
        )

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        return (
            self.db_session.query(Agent)
            .filter(Agent.id == agent_id, Agent.active)
            .first()
        )

    def assign_phone_number(self, agent_id: str, phone_number: str) -> Dict[str, Any]:
        """Assign a phone number to an agent"""
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Check if phone number is already in use
            existing_agent = self.db_session.query(Agent).filter(
                Agent.phone_number == phone_number,
                Agent.active,
                Agent.id != agent_id
            ).first()
            if existing_agent:
                return {"success": False, "error": "Phone number already in use"}

            agent.phone_number = phone_number
            self.db_session.commit()

            return {
                "success": True,
                "message": "Phone number assigned successfully",
                "agent_id": agent.id,
                "phone_number": phone_number
            }

        except Exception as e:
            self.db_session.rollback()
            return {"success": False, "error": str(e)}

    def get_agents_without_phone(self, user_id: str) -> List[Agent]:
        """Get agents for a user that don't have phone numbers assigned"""
        return self.db_session.query(Agent).filter(
            Agent.user_id == user_id,
            Agent.phone_number.is_(None),
            Agent.active
        ).all()

    async def get_customer_context(
            self,
            phone_number: str,
            agent_id: str,
            lookback_days: int = 90,
            max_conversations: int = 10
    ) -> Dict[str, Any]:
        """Get comprehensive customer context from previous conversations."""
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return self._empty_context("Agent not found")

            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            previous_conversations = (
                self.db_session.query(Conversation)
                .filter(
                    and_(
                        Conversation.caller_phone == phone_number,
                        Conversation.agent_id == agent.id,
                        Conversation.created_at >= cutoff_date,
                        Conversation.summary.isnot(None),
                        Conversation.summary != ""
                    )
                )
                .order_by(desc(Conversation.created_at))
                .limit(max_conversations)
                .all()
            )

            if not previous_conversations:
                return self._empty_context("No previous conversations found")

            return await self._build_customer_context(
                previous_conversations,
                phone_number
            )

        except Exception as e:
            app_logger.exception("Error getting customer context: %s", str(e))
            return self._empty_context(f"Error: {str(e)}")

    async def _build_customer_context(
            self,
            conversations: List[Conversation],
            phone_number: str
    ) -> Dict[str, Any]:
        """Build comprehensive customer context from conversation history."""
        summaries = []
        total_calls = len(conversations)
        conversation_types = {}
        recent_topics = []
        customer_preferences = []

        for conv in conversations:
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
            conv_type = conv.conversation_type
            conversation_types[conv_type] = conversation_types.get(conv_type, 0) + 1
            if len(recent_topics) < 15:
                recent_topics.extend(summary_data.get("topics", []))
            customer_preferences.extend(summary_data.get("preferences", []))

        latest_conversation = summaries[0] if summaries else None
        interaction_frequency = self._calculate_interaction_frequency(conversations)
        preferred_contact_type = max(conversation_types.items(), key=lambda x: x[1])[
            0] if conversation_types else "voice"

        context_summary = self._build_context_summary(
            phone_number=phone_number,
            total_calls=total_calls,
            latest_conversation=latest_conversation,
            recent_topics=list(set(recent_topics[:10])),
            preferred_contact=preferred_contact_type,
            interaction_frequency=interaction_frequency,
            customer_preferences=list(set(customer_preferences[:5]))
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
            "detailed_summaries": summaries[:5],
            "lookback_period": f"Last {len(conversations)} conversations"
        }

    def _parse_summary(self, summary: str) -> Dict[str, Any]:
        """Parse conversation summary (JSON or plain text)."""
        try:
            import json
            if summary.strip().startswith('{'):
                return json.loads(summary)
        except Exception:
            pass
        return {"summary": summary, "key_points": [], "sentiment": "neutral", "topics": [], "outcome": "completed",
                "preferences": []}

    def _calculate_duration(self, conversation: Conversation) -> Optional[int]:
        """Calculate conversation duration in minutes."""
        if conversation.ended_at and conversation.created_at:
            return int((conversation.ended_at - conversation.created_at).total_seconds() / 60)
        return None

    def _calculate_interaction_frequency(self, conversations: List[Conversation]) -> str:
        """Calculate how frequently customer contacts."""
        if len(conversations) < 2:
            return "new_customer"
        total_days = (conversations[0].created_at - conversations[-1].created_at).days
        avg_days_between = total_days / (len(conversations) - 1) if len(conversations) > 1 else 0
        if avg_days_between <= 7:
            return "frequent"
        elif avg_days_between <= 30:
            return "regular"
        else:
            return "occasional"

    def _build_context_summary(self, phone_number: str, total_calls: int, latest_conversation: Optional[Dict],
                               recent_topics: List[str], preferred_contact: str, interaction_frequency: str,
                               customer_preferences: List[str]) -> str:
        """Build a concise context summary for the agent prompt."""
        context_parts = [f"RETURNING CUSTOMER: {phone_number}"]
        frequency_desc = {"frequent": "calls frequently (weekly or more)", "regular": "calls regularly (monthly)",
                          "occasional": "calls occasionally", "new_customer": "new customer"}
        context_parts.append(
            f"History: {total_calls} previous conversations, {frequency_desc.get(interaction_frequency, 'unknown pattern')}")
        if latest_conversation:
            days_ago = (datetime.now() - datetime.strptime(latest_conversation["date"], "%Y-%m-%d")).days
            time_desc = "earlier today" if days_ago == 0 else "yesterday" if days_ago == 1 else f"{days_ago} days ago" if days_ago <= 7 else f"on {latest_conversation['date']}"
            context_parts.append(
                f"Last contact: {time_desc} - {latest_conversation.get('summary', 'No summary')[:100]}")
        if recent_topics:
            context_parts.append(f"Recent topics: {', '.join(recent_topics[:5])}")
        if customer_preferences:
            context_parts.append(f"Preferences: {', '.join(customer_preferences[:3])}")
        if preferred_contact != "voice":
            context_parts.append(f"Usually contacts via: {preferred_contact}")
        return " | ".join(context_parts)

    def _empty_context(self, reason: str) -> Dict[str, Any]:
        """Return empty context structure."""
        return {"has_history": False, "phone_number": "", "total_previous_calls": 0,
                "context_summary": "NEW CUSTOMER: No previous interaction history", "reason": reason,
                "detailed_summaries": [], "recent_topics": [], "customer_preferences": [], "lookback_period": "N/A"}

    async def query_agent_knowledge(self, agent_id: str, query: str, date_from: Optional[datetime] = None,
                                    date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Query agent's knowledge base and conversation history."""
        try:
            date_from, date_to = normalize_date_range(date_from, date_to)
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}
            context_data = self._gather_context_data(agent_id, date_from, date_to)
            collection_details = self.collection_service.get_agent_collections(agent_id)
            if self.model:
                response = await self._generate_ai_response(query, context_data, collection_details, agent)
            else:
                response = "Google Generative AI not configured. Please set the GEMINI_API_KEY environment variable."
            return {"success": True, "response": response,
                    "context_summary": {"conversations_count": len(context_data.get("conversations", [])),
                                        "messages_count": len(context_data.get("messages", [])),
                                        "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()}}}
        except Exception as e:
            app_logger.error(f"Error querying agent knowledge: {e}")
            return {"success": False, "error": str(e)}

    def _gather_context_data(self, agent_id: str, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Gather conversation context within a specified date range."""
        conversations = self.db_session.query(Conversation).filter(
            and_(Conversation.agent_id == agent_id, Conversation.started_at >= date_from,
                 Conversation.started_at <= date_to, Conversation.active)).order_by(desc(Conversation.started_at)).all()
        conversation_ids = [conv.id for conv in conversations]
        messages = []
        if conversation_ids:
            messages = self.db_session.query(Message).filter(Message.conversation_id.in_(conversation_ids),
                                                             Message.active).order_by(Message.sequence_number).all()
        conversation_summaries = [
            {"id": conv.id, "caller_phone": conv.caller_phone, "type": conv.conversation_type, "status": conv.status,
             "started_at": conv.started_at.isoformat(), "summary": conv.summary or "No summary available",
             "duration_seconds": conv.duration_seconds} for conv in conversations]
        message_summaries = [
            {"role": msg.role, "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
             "created_at": msg.created_at.isoformat()} for msg in messages[-50:]]
        return {"conversations": conversation_summaries, "messages": message_summaries,
                "total_conversations": len(conversations), "total_messages": len(messages)}

    async def _generate_ai_response(self, query: str, context_data: Dict[str, Any],
                                    collection_details: List[Dict[str, Any]], agent: Agent) -> str:
        """Generate AI response using Google Generative AI with tool calling capabilities."""
        try:
            # Build collection details string for the agent config
            collections = self.db_session.query(Collection).filter(
                Collection.agent_id == agent.id,
                Collection.active == True,
                Collection.status == "ready"
            ).all()

            collection_data = []
            for collection in collections:
                collection_data.append({
                    "collection_name": collection.name,
                    "display_name": collection.display_name,
                    "description": collection.description or "No description provided",
                    "notes": collection.notes or "No specific rules provided"
                })

            collection_prompt = AgentConfigBuilder.format_collections_prompt(collection_data)
            agent_config = self.build_agent_config(agent, collection_details=collection_prompt)
            system_prompt = agent_config.get("llm_config", {}).get("system_prompt", agent.system_prompt)
            context_prompt = self._build_agent_context_prompt(query, context_data, system_prompt, collection_details)
            function_declarations = self._build_function_declarations(agent.tools or [])

            response = await self.model.generate_content_async(
                context_prompt,
                tools=function_declarations or None
            )
            return await self._process_ai_response(response, agent)
        except Exception as e:
            app_logger.error(f"AI generation error: {e}")
            return f"AI generation error: {str(e)}"

    def _build_agent_context_prompt(self, query: str, context_data: Dict[str, Any], system_prompt: str = "",
                                    collections: list[dict] = None) -> str:
        """Build a comprehensive context prompt for the agent, including collection details."""
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

    def _build_function_declarations(self, agent_tools: List[str]) -> List[Tool]:
        """Build function declarations for Google Generative AI function calling using Vertex AI Tool format."""
        tool_schemas = {"search_collection": {"name": "search_collection",
                                              "description": "Searches a specific collection for relevant information.",
                                              "parameters": {"type": "object", "properties": {
                                                  "collection_name": {"type": "string",
                                                                      "description": "The name of the collection to search."},
                                                  "query": {"type": "string",
                                                            "description": "The user's query to search for."},
                                                  "k": {"type": "integer",
                                                        "description": "The number of results to return.",
                                                        "default": 10}}, "required": ["collection_name", "query"]}}}

        function_declarations = []
        for tool_name in agent_tools:
            if tool_name in tool_schemas:
                schema = tool_schemas[tool_name]
                function_declarations.append(
                    FunctionDeclaration(
                        name=schema["name"],
                        description=schema["description"],
                        parameters=schema["parameters"],
                    )
                )

        if not function_declarations:
            return []

        return [Tool(function_declarations=function_declarations)]

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
                    tool_result = await self._execute_tool(function_call.name, dict(function_call.args), agent)
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
            tool_params.update({"agent_id": agent.id})
            tool_function = FUNCTION_MAP[tool_name]
            result = await tool_function(**tool_params)
            app_logger.info(f"Executed tool '{tool_name}' for agent {agent.id}: Success={result.get('success', False)}")
            return result
        except Exception as e:
            app_logger.error(f"Error executing tool '{tool_name}': {e}")
            return {"success": False, "error": str(e)}

    def build_comprehensive_agent_config(self, agent: Agent) -> Dict[str, Any]:
        """Build agent configuration with full context including collections and business details"""
        try:
            # Get agent's collections
            collections = self.db_session.query(Collection).filter(
                Collection.agent_id == agent.id,
                Collection.active == True,
                Collection.status == "ready"
            ).all()

            # Build collection details using the format_collections_prompt method
            collection_data = []
            for collection in collections:
                collection_data.append({
                    "collection_name": collection.name,
                    "display_name": collection.display_name,
                    "description": collection.description or "No description provided",
                    "notes": collection.notes or "No specific rules provided"
                })

            collection_details = AgentConfigBuilder.format_collections_prompt(collection_data)

            # Build business context from agent data
            business_context = self._build_business_context(agent)

            # Use the comprehensive build method
            return AgentConfigBuilder.build_agent_config(
                agent,
                customer_context=business_context,
                collection_details=collection_details
            )
        except Exception as e:
            app_logger.error(f"Failed to build comprehensive agent config for agent {agent.id}: {str(e)}")
            # Return fallback configuration
            return self.build_agent_config(agent)

    def _build_business_context(self, agent: Agent) -> str:
        """Build business context from agent configuration"""
        context_parts = []

        # Business hours context
        if agent.business_hours:
            days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday",
                        7: "Sunday"}
            business_days = [days_map.get(day, str(day)) for day in agent.business_hours.get("days", [1, 2, 3, 4, 5])]
            start_time = agent.business_hours.get("start", "09:00")
            end_time = agent.business_hours.get("end", "17:00")
            timezone = agent.business_hours.get("timezone", "UTC")

            context_parts.append(
                f"Business operates {', '.join(business_days)} from {start_time} to {end_time} ({timezone})")

        # Appointment settings
        if agent.booking_enabled:
            if agent.default_slot_duration:
                context_parts.append(f"Default appointment duration is {agent.default_slot_duration} minutes")

            if agent.buffer_time:
                context_parts.append(f"Buffer time between appointments is {agent.buffer_time} minutes")

            if agent.max_slot_appointments:
                if agent.max_slot_appointments == 1:
                    context_parts.append("No overlapping appointments allowed")
                else:
                    context_parts.append(f"Maximum {agent.max_slot_appointments} appointments per time slot")

            if agent.blocked_dates:
                blocked_dates_str = ", ".join(agent.blocked_dates)
                context_parts.append(f"Unavailable dates: {blocked_dates_str}")
        else:
            context_parts.append("Appointment booking is currently disabled")

        # User information
        if agent.user:
            try:
                company_name = agent.user.name if hasattr(agent.user, 'name') else "the business"
            except AttributeError:
                pass

        return ". ".join(context_parts) if context_parts else ""
