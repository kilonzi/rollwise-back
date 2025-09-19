from __future__ import annotations

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Agent, Tenant, Conversation, Message, Collection
from app.utils.agent_config_builder import AgentConfigBuilder
from app.services.calendar_service import CalendarService
from app.utils.logging_config import app_logger
from app.config.settings import settings
import google.generativeai as genai
from app.config.agent_functions import FUNCTION_MAP
from app.utils.date_utils import normalize_date_range
from sqlalchemy import and_, desc
from app.services.collection_service import CollectionService


class AgentService:
    """Service for managing AI agents and their configurations"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.collection_service = CollectionService(db_session)
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(settings.GEMINI_LLM_MODEL)
        else:
            self.model = None

    def build_agent_config(self, agent: Agent, customer_context: str = "", dataset_details: str = "", collection_details: str = "") -> Dict[str, Any]:
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
        """Get agent by phone number with active tenant check"""
        return (
            self.db_session.query(Agent)
            .join(Tenant)
            .filter(
                Agent.phone_number == phone_number,
                Agent.active,
                Tenant.active,
            )
            .first()
        )

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID with active tenant check"""
        return (
            self.db_session.query(Agent)
            .join(Tenant)
            .filter(Agent.id == agent_id, Agent.active, Tenant.active)
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

    def get_agents_without_phone(self, tenant_id: str = None) -> List[Agent]:
        """Get agents that don't have phone numbers assigned"""
        query = self.db_session.query(Agent).filter(
            Agent.phone_number.is_(None),
            Agent.active
        )

        if tenant_id:
            query = query.filter(Agent.tenant_id == tenant_id)

        return query.all()

    def create_agent_with_calendar(self,
                                 tenant_id: str,
                                 name: str,
                                 greeting: str,
                                 system_prompt: str,
                                 voice_model: str = "aura-2-thalia-en",
                                 language: str = "en",
                                 business_hours: Optional[Dict[str, Any]] = None,
                                 default_slot_duration: int = 30,
                                 max_slot_appointments: int = 1,
                                 buffer_time: int = 15) -> Dict[str, Any]:
        """Create a new agent with integrated calendar"""
        try:
            # Create agent record
            agent_id = str(uuid.uuid4())

            # Default business hours if not provided
            if business_hours is None:
                business_hours = {
                    "start": "09:00",
                    "end": "17:00",
                    "timezone": "UTC",
                    "days": [1, 2, 3, 4, 5]  # Monday to Friday
                }

            agent = Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name=name,
                greeting=greeting,
                system_prompt=system_prompt,
                voice_model=voice_model,
                language=language,
                business_hours=business_hours,
                default_slot_duration=default_slot_duration,
                max_slot_appointments=max_slot_appointments,
                buffer_time=buffer_time,
                tools=["create_calendar_event", "cancel_calendar_event", "search_calendar_events",
                       "update_calendar_event", "list_calendar_events"]  # Include calendar tools
            )

            # Add to database but don't commit yet
            self.db_session.add(agent)
            self.db_session.flush()  # Get the ID without committing

            # Create Google Calendar for the agent
            calendar_service = CalendarService()
            try:
                calendar_id = calendar_service.create_agent_calendar(agent.id, name)
                agent.calendar_id = calendar_id
                app_logger.info(f"Created calendar {calendar_id} for agent {agent.id}")
            except Exception as calendar_error:
                app_logger.warning(f"Failed to create calendar for agent {agent.id}: {str(calendar_error)}")
                # Continue without calendar - can be added later
                pass

            # Commit the transaction
            self.db_session.commit()
            self.db_session.refresh(agent)

            app_logger.info(f"Created agent {agent.id} with calendar integration")

            return {
                "success": True,
                "agent": {
                    "id": agent.id,
                    "name": agent.name,
                    "calendar_id": agent.calendar_id,
                    "business_hours": agent.business_hours,
                    "default_slot_duration": agent.default_slot_duration,
                    "max_slot_appointments": agent.max_slot_appointments,
                    "buffer_time": agent.buffer_time,
                    "has_calendar": agent.calendar_id is not None
                }
            }

        except Exception as e:
            self.db_session.rollback()
            app_logger.error(f"Failed to create agent with calendar: {str(e)}")
            return {"success": False, "error": str(e)}

    def setup_agent_calendar(self, agent_id: str) -> Dict[str, Any]:
        """Setup calendar for an existing agent that doesn't have one"""
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            if agent.calendar_id:
                return {"success": False, "error": "Agent already has a calendar"}

            # Create Google Calendar for the agent
            calendar_service = CalendarService()
            calendar_id = calendar_service.create_agent_calendar(agent.id, agent.name)

            # Update agent with calendar ID
            agent.calendar_id = calendar_id

            # Add calendar tools if not already present
            current_tools = agent.tools or []
            calendar_tools = ["create_calendar_event", "cancel_calendar_event", "search_calendar_events",
                            "update_calendar_event", "list_calendar_events"]

            for tool in calendar_tools:
                if tool not in current_tools:
                    current_tools.append(tool)

            agent.tools = current_tools
            agent.updated_at = datetime.now(timezone.utc)

            self.db_session.commit()

            app_logger.info(f"Setup calendar {calendar_id} for existing agent {agent_id}")

            return {
                "success": True,
                "calendar_id": calendar_id,
                "message": "Calendar setup successfully"
            }

        except Exception as e:
            self.db_session.rollback()
            app_logger.error(f"Failed to setup calendar for agent {agent_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def build_comprehensive_context(
        self,
        agent: Agent,
        caller_phone: str = "",
        include_customer_history: bool = True,
        include_datasets: bool = True,
        include_tools: bool = True,
        include_business_info: bool = True
    ) -> Dict[str, Any]:
        """Build comprehensive context for the agent."""
        context_sections = []
        context_data = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "tenant_id": str(agent.tenant_id),
            "timestamp": datetime.now().isoformat()
        }

        try:
            if include_customer_history and caller_phone and caller_phone != "unknown":
                customer_context = await self.get_customer_context(caller_phone, agent.id)
                if customer_context["has_history"]:
                    context_sections.append(customer_context["context_summary"])
                    context_data["customer_history"] = customer_context
                else:
                    context_sections.append("NEW CUSTOMER: No previous interaction history")

            if include_datasets:
                collections_context = await self._get_collections_context(agent)
                if collections_context["collections"]:
                    context_sections.append(collections_context["context_summary"])
                    context_data["collections"] = collections_context

            if include_tools:
                tools_context = self._get_tools_context(agent)
                if tools_context["available_tools"]:
                    context_sections.append(tools_context["context_summary"])
                    context_data["tools"] = tools_context

            if include_business_info:
                business_context = self._get_business_context(agent)
                if business_context["context_summary"]:
                    context_sections.append(business_context["context_summary"])
                    context_data["business"] = business_context

            status_context = self._get_status_context(agent)
            context_sections.append(status_context["context_summary"])
            context_data["status"] = status_context

            full_context = " | ".join(filter(None, context_sections))

            return {
                "full_context": full_context,
                "sections": context_sections,
                "data": context_data,
                "has_context": len(context_sections) > 0
            }

        except Exception as e:
            app_logger.exception("Error building agent context: %s", str(e))
            return {
                "full_context": "NEW CUSTOMER: No previous interaction history",
                "sections": ["Error retrieving context"],
                "data": context_data,
                "has_context": False,
                "error": str(e)
            }

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
                        Conversation.tenant_id == agent.tenant_id,
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
                phone_number,
                agent.tenant_id
            )

        except Exception as e:
            app_logger.exception("Error getting customer context: %s", str(e))
            return self._empty_context(f"Error: {str(e)}")

    async def _build_customer_context(
        self,
        conversations: List[Conversation],
        phone_number: str,
        tenant_id: str
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
        preferred_contact_type = max(conversation_types.items(), key=lambda x: x[1])[0] if conversation_types else "voice"

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
        return {"summary": summary, "key_points": [], "sentiment": "neutral", "topics": [], "outcome": "completed", "preferences": []}

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

    def _build_context_summary(self, phone_number: str, total_calls: int, latest_conversation: Optional[Dict], recent_topics: List[str], preferred_contact: str, interaction_frequency: str, customer_preferences: List[str]) -> str:
        """Build a concise context summary for the agent prompt."""
        context_parts = [f"RETURNING CUSTOMER: {phone_number}"]
        frequency_desc = {"frequent": "calls frequently (weekly or more)", "regular": "calls regularly (monthly)", "occasional": "calls occasionally", "new_customer": "new customer"}
        context_parts.append(f"History: {total_calls} previous conversations, {frequency_desc.get(interaction_frequency, 'unknown pattern')}")
        if latest_conversation:
            days_ago = (datetime.now() - datetime.strptime(latest_conversation["date"], "%Y-%m-%d")).days
            time_desc = "earlier today" if days_ago == 0 else "yesterday" if days_ago == 1 else f"{days_ago} days ago" if days_ago <= 7 else f"on {latest_conversation['date']}"
            context_parts.append(f"Last contact: {time_desc} - {latest_conversation.get('summary', 'No summary')[:100]}")
        if recent_topics:
            context_parts.append(f"Recent topics: {', '.join(recent_topics[:5])}")
        if customer_preferences:
            context_parts.append(f"Preferences: {', '.join(customer_preferences[:3])}")
        if preferred_contact != "voice":
            context_parts.append(f"Usually contacts via: {preferred_contact}")
        return " | ".join(context_parts)

    def _empty_context(self, reason: str) -> Dict[str, Any]:
        """Return empty context structure."""
        return {"has_history": False, "phone_number": "", "total_previous_calls": 0, "context_summary": "NEW CUSTOMER: No previous interaction history", "reason": reason, "detailed_summaries": [], "recent_topics": [], "customer_preferences": [], "lookback_period": "N/A"}

    async def query_agent_knowledge(self, agent_id: str, query: str, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Query agent's knowledge base and conversation history."""
        try:
            date_from, date_to = normalize_date_range(date_from, date_to)
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}
            context_data = self._gather_context_data(agent_id, agent.tenant_id, date_from, date_to)
            collection_details = self.collection_service.get_agent_collections(agent_id)
            if self.model:
                response = await self._generate_ai_response(query, context_data, collection_details, agent)
            else:
                response = "Google Generative AI not configured. Please set the GEMINI_API_KEY environment variable."
            return {"success": True, "response": response, "context_summary": {"conversations_count": len(context_data.get("conversations", [])), "messages_count": len(context_data.get("messages", [])), "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()}}}
        except Exception as e:
            app_logger.error(f"Error querying agent knowledge: {e}")
            return {"success": False, "error": str(e)}

    def _gather_context_data(self, agent_id: str, tenant_id: str, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """Gather conversation context within a specified date range."""
        conversations = self.db_session.query(Conversation).filter(and_(Conversation.agent_id == agent_id, Conversation.tenant_id == tenant_id, Conversation.started_at >= date_from, Conversation.started_at <= date_to, Conversation.active)).order_by(desc(Conversation.started_at)).all()
        conversation_ids = [conv.id for conv in conversations]
        messages = []
        if conversation_ids:
            messages = self.db_session.query(Message).filter(Message.conversation_id.in_(conversation_ids), Message.active).order_by(Message.sequence_number).all()
        conversation_summaries = [{"id": conv.id, "caller_phone": conv.caller_phone, "type": conv.conversation_type, "status": conv.status, "started_at": conv.started_at.isoformat(), "summary": conv.summary or "No summary available", "duration_seconds": conv.duration_seconds} for conv in conversations]
        message_summaries = [{"role": msg.role, "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content, "created_at": msg.created_at.isoformat()} for msg in messages[-50:]]
        return {"conversations": conversation_summaries, "messages": message_summaries, "total_conversations": len(conversations), "total_messages": len(messages)}

    async def _generate_ai_response(self, query: str, context_data: Dict[str, Any], collection_details: List[Dict[str, Any]], agent: Agent) -> str:
        """Generate AI response using Google Generative AI with tool calling capabilities."""
        try:
            agent_config = self.build_agent_config(agent, collection_details=self.get_collection_details_for_prompt(agent))
            system_prompt = agent_config["llm_config"]["system_prompt"]
            context_prompt = self._build_agent_context_prompt(query, context_data, system_prompt, collection_details)
            function_declarations = self._build_function_declarations(agent.tools)
            if function_declarations:
                model_with_tools = genai.GenerativeModel(model_name=settings.GEMINI_LLM_MODEL, tools=function_declarations)
                response = model_with_tools.generate_content(context_prompt)
            else:
                response = self.model.generate_content(context_prompt)
            return await self._process_ai_response(response, agent)
        except Exception as e:
            app_logger.error(f"AI generation error: {e}")
            return f"AI generation error: {str(e)}"

    def _build_agent_context_prompt(self, query: str, context_data: Dict[str, Any], system_prompt: str = "", collections: list[dict] = None) -> str:
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

    def _build_function_declarations(self, agent_tools: List[str]) -> List[Dict[str, Any]]:
        """Build function declarations for Google Generative AI function calling."""
        tool_schemas = {"search_collection": {"name": "search_collection", "description": "Searches a specific collection for relevant information.", "parameters": {"type": "object", "properties": {"collection_name": {"type": "string", "description": "The name of the collection to search."}, "query": {"type": "string", "description": "The user's query to search for."}, "k": {"type": "integer", "description": "The number of results to return.", "default": 10}}, "required": ["collection_name", "query"]}}}
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
            tool_params.update({"agent_id": agent.id, "tenant_id": agent.tenant_id})
            tool_function = FUNCTION_MAP[tool_name]
            result = await tool_function(**tool_params)
            app_logger.info(f"Executed tool '{tool_name}' for agent {agent.id}: Success={result.get('success', False)}")
            return result
        except Exception as e:
            app_logger.error(f"Error executing tool '{tool_name}': {e}")
            return {"success": False, "error": str(e)}
