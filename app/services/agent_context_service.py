"""
Agent Context Service

Builds comprehensive context for agents including customer history,
available datasets, tools, business constraints, and capabilities.
"""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Agent, Collection
from app.services.customer_context_service import CustomerContextService


class AgentContextService:
    """
    Service for building comprehensive agent context including:
    - Customer interaction history
    - Available datasets and knowledge bases
    - Business tools and capabilities
    - Business constraints and policies
    - Current business status
    """

    def __init__(self, db_session: Session):
        self.db_session = db_session

    async def build_comprehensive_context(
        self,
        agent: Agent,
        caller_phone: str = "",
        include_customer_history: bool = True,
        include_datasets: bool = True,
        include_tools: bool = True,
        include_business_info: bool = True
    ) -> Dict[str, Any]:
        """
        Build comprehensive context for the agent.

        Args:
            agent: Agent database object
            caller_phone: Customer's phone number for history lookup
            include_customer_history: Whether to include customer interaction history
            include_datasets: Whether to include available datasets information
            include_tools: Whether to include available tools information
            include_business_info: Whether to include business constraints and info

        Returns:
            Dict containing all context information and formatted context string
        """
        context_sections = []
        context_data = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "tenant_id": str(agent.tenant_id),
            "timestamp": datetime.now().isoformat()
        }

        try:
            # 1. Customer History Context
            if include_customer_history and caller_phone and caller_phone != "unknown":
                customer_context = await self._get_customer_context(agent.id, caller_phone)
                if customer_context["has_history"]:
                    context_sections.append(customer_context["context_summary"])
                    context_data["customer_history"] = customer_context
                else:
                    context_sections.append("NEW CUSTOMER: No previous interaction history")

            # 2. Available Collections Context
            if include_datasets:
                collections_context = await self._get_collections_context(agent)
                if collections_context["collections"]:
                    context_sections.append(collections_context["context_summary"])
                    context_data["collections"] = collections_context

            # 3. Tools and Capabilities Context
            if include_tools:
                tools_context = self._get_tools_context(agent)
                if tools_context["available_tools"]:
                    context_sections.append(tools_context["context_summary"])
                    context_data["tools"] = tools_context

            # 4. Business Information Context
            if include_business_info:
                business_context = self._get_business_context(agent)
                if business_context["context_summary"]:
                    context_sections.append(business_context["context_summary"])
                    context_data["business"] = business_context

            # 5. Current Status Context
            status_context = self._get_status_context(agent)
            context_sections.append(status_context["context_summary"])
            context_data["status"] = status_context

            # Combine all context sections
            full_context = " | ".join(filter(None, context_sections))

            return {
                "full_context": full_context,
                "sections": context_sections,
                "data": context_data,
                "has_context": len(context_sections) > 0
            }

        except Exception as e:
            print(f"⚠️ Error building agent context: {str(e)}")
            return {
                "full_context": "NEW CUSTOMER: No previous interaction history",
                "sections": ["Error retrieving context"],
                "data": context_data,
                "has_context": False,
                "error": str(e)
            }

    async def _get_customer_context(self, agent_id: str, caller_phone: str) -> Dict[str, Any]:
        """Get customer interaction history."""
        try:
            customer_service = CustomerContextService(self.db_session)
            return await customer_service.get_customer_context(caller_phone, agent_id)
        except Exception as e:
            print(f"⚠️ Error getting customer context: {str(e)}")
            return {"has_history": False, "context_summary": "NEW CUSTOMER: No previous interaction history"}

    async def _get_collections_context(self, agent: Agent) -> Dict[str, Any]:
        """Get information about available collections and knowledge bases."""
        try:
            # Query collections for this agent
            collections = (
                self.db_session.query(Collection)
                .filter(
                    Collection.agent_id == agent.id,
                    Collection.active,
                    Collection.status == "ready"
                )
                .all()
            )

            if not collections:
                return {
                    "collections": [],
                    "context_summary": "",
                    "total_collections": 0
                }

            # Build collection information
            collection_info = []
            collections_summary = []

            for collection in collections:
                collection_info.append({
                    "name": collection.name,
                    "display_name": collection.display_name,
                    "description": collection.description or "",
                    "content_type": collection.content_type or "general",
                    "file_type": collection.file_type or "text",
                    "chunk_count": collection.chunk_count,
                    "created_at": collection.created_at.strftime("%Y-%m-%d") if collection.created_at else "Unknown"
                })

                # Add to summary
                chunk_info = f"{collection.chunk_count} chunks" if collection.chunk_count else "processing"
                collections_summary.append(f"{collection.name} ({chunk_info})")

            # Build context summary
            context_summary = f"COLLECTIONS AVAILABLE: {len(collections)} document collections: {', '.join(collections_summary)}. Use search_collection(collection_name='name', query='search terms') to query this information."

            return {
                "collections": collection_info,
                "context_summary": context_summary,
                "total_collections": len(collections),
                "collection_names": [c.name for c in collections]
            }

        except Exception as e:
            print(f"⚠️ Error getting collections context: {str(e)}")
            return {
                "collections": [],
                "context_summary": "",
                "total_collections": 0,
                "error": str(e)
            }

    def _get_tools_context(self, agent: Agent) -> Dict[str, Any]:
        """Get information about available tools and capabilities."""
        try:
            # Get tools from agent configuration
            available_tools = agent.tools if agent.tools else []

            # Categorize tools
            tool_categories = {
                "calendar": [],
                "knowledge": [],
                "business": [],
                "communication": [],
                "other": []
            }

            tool_descriptions = {
                # Calendar tools
                "create_calendar_event": "Book appointments and create calendar events",
                "list_calendar_events": "Check availability and list scheduled appointments",
                "cancel_calendar_event": "Cancel existing appointments",
                "search_calendar_events": "Search for specific appointments or time slots",
                "update_calendar_event": "Modify existing appointments",

                # Knowledge tools
                "search_agent_dataset": "Search business knowledge bases and datasets",
                "search_business_knowledge_base": "Search static business information",

                # Business tools
                "hangup_function": "End the conversation gracefully",

                # Add more tool descriptions as needed
            }

            for tool in available_tools:
                if "calendar" in tool:
                    tool_categories["calendar"].append(tool)
                elif "search" in tool or "dataset" in tool or "knowledge" in tool:
                    tool_categories["knowledge"].append(tool)
                elif "hangup" in tool:
                    tool_categories["communication"].append(tool)
                else:
                    tool_categories["other"].append(tool)

            # Build capabilities summary
            capabilities = []
            if tool_categories["calendar"]:
                capabilities.append(f"Calendar management ({len(tool_categories['calendar'])} tools)")
            if tool_categories["knowledge"]:
                capabilities.append(f"Knowledge search ({len(tool_categories['knowledge'])} tools)")
            if tool_categories["communication"]:
                capabilities.append("Call management")
            if tool_categories["other"]:
                capabilities.append(f"Additional tools ({len(tool_categories['other'])})")

            context_summary = ""
            if capabilities:
                context_summary = f"CAPABILITIES: {', '.join(capabilities)}. Total {len(available_tools)} tools available."

            return {
                "available_tools": available_tools,
                "tool_categories": tool_categories,
                "tool_descriptions": {tool: tool_descriptions.get(tool, "Tool available") for tool in available_tools},
                "context_summary": context_summary,
                "total_tools": len(available_tools)
            }

        except Exception as e:
            print(f"⚠️ Error getting tools context: {str(e)}")
            return {
                "available_tools": [],
                "context_summary": "",
                "total_tools": 0,
                "error": str(e)
            }

    def _get_business_context(self, agent: Agent) -> Dict[str, Any]:
        """Get business constraints, policies, and information."""
        try:
            business_info = []

            # Business hours
            if agent.business_hours:
                hours = agent.business_hours
                days_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
                business_days = [days_map.get(day, str(day)) for day in hours.get("days", [1,2,3,4,5])]
                start_time = hours.get("start", "09:00")
                end_time = hours.get("end", "17:00")
                timezone = hours.get("timezone", "UTC")
                business_info.append(f"Hours: {'-'.join(business_days)} {start_time}-{end_time} {timezone}")

            # Booking settings
            if agent.booking_enabled:
                booking_details = []
                if agent.default_slot_duration:
                    booking_details.append(f"{agent.default_slot_duration}min slots")
                if agent.max_slot_appointments and agent.max_slot_appointments > 1:
                    booking_details.append(f"max {agent.max_slot_appointments} per slot")
                if agent.buffer_time:
                    booking_details.append(f"{agent.buffer_time}min buffer")

                booking_info = "Booking enabled"
                if booking_details:
                    booking_info += f" ({', '.join(booking_details)})"
                business_info.append(booking_info)
            else:
                business_info.append("Booking disabled")

            # Tenant information
            if agent.tenant:
                if hasattr(agent.tenant, 'name') and agent.tenant.name:
                    business_info.append(f"Business: {agent.tenant.name}")
                if hasattr(agent.tenant, 'business_type') and agent.tenant.business_type:
                    business_info.append(f"Type: {agent.tenant.business_type}")

            # Calendar integration
            if agent.calendar_id:
                business_info.append("Google Calendar integrated")

            context_summary = ""
            if business_info:
                context_summary = f"BUSINESS INFO: {' | '.join(business_info)}"

            return {
                "business_hours": agent.business_hours,
                "booking_enabled": agent.booking_enabled,
                "booking_settings": {
                    "slot_duration": agent.default_slot_duration,
                    "max_appointments": agent.max_slot_appointments,
                    "buffer_time": agent.buffer_time
                },
                "calendar_integrated": bool(agent.calendar_id),
                "tenant_info": {
                    "name": getattr(agent.tenant, 'name', None) if agent.tenant else None,
                    "business_type": getattr(agent.tenant, 'business_type', None) if agent.tenant else None
                },
                "context_summary": context_summary,
                "raw_info": business_info
            }

        except Exception as e:
            print(f"⚠️ Error getting business context: {str(e)}")
            return {
                "context_summary": "",
                "error": str(e)
            }

    def _get_status_context(self, agent: Agent) -> Dict[str, Any]:
        """Get current status and operational information."""
        try:
            current_time = datetime.now()

            # Check if currently in business hours
            in_business_hours = self._is_in_business_hours(agent, current_time)

            # Voice and language settings
            voice_model = agent.voice_model or "aura-2-thalia-en"
            language = agent.language or "en"

            status_info = []
            status_info.append(f"Voice: {voice_model}")
            status_info.append(f"Language: {language}")

            if in_business_hours:
                status_info.append("Currently OPEN")
            else:
                status_info.append("Currently CLOSED")

            context_summary = f"STATUS: {' | '.join(status_info)} | Current time: {current_time.strftime('%Y-%m-%d %H:%M %Z')}"

            return {
                "current_time": current_time.isoformat(),
                "in_business_hours": in_business_hours,
                "voice_model": voice_model,
                "language": language,
                "agent_active": agent.active,
                "context_summary": context_summary
            }

        except Exception as e:
            print(f"⚠️ Error getting status context: {str(e)}")
            return {
                "context_summary": f"STATUS: Voice {agent.voice_model or 'default'} | Active: {agent.active}",
                "error": str(e)
            }

    def _is_in_business_hours(self, agent: Agent, current_time: datetime) -> bool:
        """Check if current time is within business hours."""
        try:
            if not agent.business_hours:
                return True  # If no hours set, assume always open

            hours = agent.business_hours
            current_weekday = current_time.weekday() + 1  # Monday = 1
            business_days = hours.get("days", [1, 2, 3, 4, 5])

            if current_weekday not in business_days:
                return False

            # Simple time check (could be enhanced for timezone support)
            start_hour = int(hours.get("start", "09:00").split(":")[0])
            end_hour = int(hours.get("end", "17:00").split(":")[0])
            current_hour = current_time.hour

            return start_hour <= current_hour < end_hour

        except Exception:
            return True  # Default to open if parsing fails

    def get_collection_details_for_prompt(self, agent: Agent) -> str:
        """
        Get detailed collection information formatted for agent prompts.
        This provides specific guidance on what data is available and how to access it.
        """
        try:
            collections = (
                self.db_session.query(Collection)
                .filter(
                    Collection.agent_id == agent.id,
                    Collection.active,
                    Collection.status == "ready"
                )
                .all()
            )

            if not collections:
                return ""

            collection_count = len(collections)

            # Build the formatted prompt matching the requested format
            prompt_parts = [
                f"You have been provided with {collection_count} collection{'s' if collection_count != 1 else ''}. These collections are your only sources of truth.",
                "Do not rely on external information. Do not hallucinate.",
                "",
                "Here are the collections:"
            ]

            for i, collection in enumerate(collections, 1):
                description = collection.description or "General information and data"
                notes = collection.notes or ""

                # Build the collection line
                collection_line = f"{i}. {collection.display_name} — Purpose: {description}."

                if notes:
                    collection_line += f" Key rules: {notes}."

                prompt_parts.append(collection_line)

            prompt_parts.extend([
                "",
                "When answering a user query:",
                "- Select the most relevant collection(s).",
                "- Call `search_collection(collection_name, query, limit=50)` to retrieve results.",
                "- Read the retrieved snippets carefully.",
                "- Answer strictly based on retrieved content.",
                "- If snippets do not contain the answer, say \"I don't know.\"",
                "",
                "Available collection names for search_collection function:"
            ])

            for collection in collections:
                prompt_parts.append(f"- \"{collection.name}\" (for {collection.display_name})")

            return "\n".join(prompt_parts)


        except Exception as e:
            print(f"⚠️ Error getting collection details: {str(e)}")
            return f"Error retrieving collection information: {str(e)}"