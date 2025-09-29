"""
Unified Context Builder Service

This service consolidates all agent configuration and context building logic,
including business details, menu items, conversation history, and order history.
"""

from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.config.agent_constants import get_platform_template
from app.models import Agent
from app.tools.registry import global_registry
from app.utils.appointment_builder import build_appointment_context
from app.utils.context_formatters import format_business_context
from app.utils.context_utils import get_phone_from_conversation, get_current_order_id
from app.utils.history_builders import (
    build_historical_conversations,
    build_historical_orders,
    build_current_conversation_context,
)
from app.utils.logging_config import app_logger
from app.utils.menu_builder import build_menu_context
from app.utils.timezone_utils import build_time_context_for_agent
from app.utils.memory_builder import build_memory_context, build_rules_and_lessons_context


class ContextBuilderService:
    """Service for building comprehensive agent context from all relevant data sources"""

    def __init__(self, db_session: Session):
        self.db_session = db_session

    def build_complete_agent_config(
            self,
            agent: Agent,
            phone_number: Optional[str] = None,
            conversation_id: Optional[str] = None,
            lookback_days: int = 90,
    ) -> Dict[str, Any]:
        """
        Build complete agent configuration with all context data

        Args:
            agent: Agent database object
            phone_number: Customer phone number for context
            conversation_id: Current conversation ID
            lookback_days: How far back to look for conversation/order history

        Returns:
            Complete agent configuration with all context
        """
        try:
            # Extract phone number from conversation if not provided
            if conversation_id and not phone_number:
                phone_number = get_phone_from_conversation(self.db_session, conversation_id)

            # Build all context components
            context_data = self._gather_context_data(
                agent, phone_number, conversation_id, lookback_days
            )

            # Build unified system prompt
            system_prompt = self._build_unified_system_prompt(agent, context_data)

            # Return complete Deepgram Agent API configuration
            return {
                "type": "Settings",
                "audio": {
                    "input": {"encoding": "mulaw", "sample_rate": 8000},
                    "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
                },
                "agent": {
                    "language": agent.language or "en",
                    "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
                    "think": {
                        "provider": {
                            "type": "open_ai",
                            "model": "gpt-4o-mini",
                            "temperature": 0.4,
                        },
                        "prompt": system_prompt,
                        "functions": self._extract_functions_from_registry(agent),
                    },
                    "speak": {
                        "provider": {
                            "type": "deepgram",
                            "model": agent.voice_model or "aura-2-thalia-en",
                        }
                    },
                    "greeting": self._build_greeting(agent),
                },
            }

        except Exception as e:
            app_logger.error(f"Failed to build complete agent config: {str(e)}")
            return self._build_fallback_config(agent)

    def _gather_context_data(
            self, agent: Agent, phone_number: Optional[str], conversation_id: Optional[str], lookback_days: int
    ) -> Dict[str, str]:
        """Gather all context data components based on agent capabilities"""
        context_data = {
            "business": format_business_context(agent),
            "menu": "",
            "current_conversation": "",
            "historical_conversations": "",
            "historical_orders": "",
            "appointments": "",
            "memories": "",
            "rules_and_lessons": "",
        }

        # Determine agent capabilities (mutually exclusive)
        ordering_enabled = getattr(agent, 'ordering_enabled', False)
        booking_enabled = getattr(agent, 'booking_enabled', False)

        # Ensure mutual exclusivity - if both are true, default to booking
        if ordering_enabled and booking_enabled:
            app_logger.warning(f"Agent {agent.id} has both ordering and booking enabled. Defaulting to booking only.")
            ordering_enabled = False
            booking_enabled = True

        # Agent memories - get both general memories and critical rules/lessons
        context_data["memories"] = build_memory_context(
            self.db_session, agent, conversation_id, limit=5
        )

        # Critical rules and lessons (separate section for high priority)
        context_data["rules_and_lessons"] = build_rules_and_lessons_context(
            self.db_session, agent
        )

        # Menu context (ONLY if ordering enabled)
        if ordering_enabled:
            context_data["menu"] = build_menu_context(self.db_session, agent)

        # Current conversation context (always include)
        if conversation_id:
            current_context, extracted_phone = build_current_conversation_context(
                self.db_session, conversation_id
            )
            context_data["current_conversation"] = current_context
            # Use extracted phone if not provided
            if not phone_number:
                phone_number = extracted_phone

        # Historical contexts (only if we have a phone number)
        if phone_number:
            context_data["historical_conversations"] = build_historical_conversations(
                self.db_session, agent.id, phone_number, lookback_days,
                exclude_conversation_id=conversation_id, limit=3
            )

            # Historical orders (ONLY if ordering enabled)
            if ordering_enabled:
                current_order_id = get_current_order_id(self.db_session, conversation_id) if conversation_id else None
                context_data["historical_orders"] = build_historical_orders(
                    self.db_session, agent.id, phone_number, lookback_days,
                    exclude_order_id=current_order_id, limit=3
                )

        # Appointment context (ONLY if booking enabled)
        if booking_enabled:
            context_data["appointments"] = build_appointment_context(
                agent, self.db_session, phone_number
            )

        return context_data

    def _build_unified_system_prompt(self, agent: Agent, context_data: Dict[str, str]) -> str:
        """Build the complete unified system prompt"""
        # Platform template for consistent tone and behavior (dynamic based on agent capabilities)
        prompt_parts = [get_platform_template(agent)]

        # Agent's custom prompt (if available and not default)
        if agent.system_prompt and agent.system_prompt.strip() != "You are a helpful AI assistant.":
            prompt_parts.append(f"AGENT PERSONALITY:\n{agent.system_prompt}\n")

        # Add critical rules and lessons EARLY in the prompt (high priority)
        if context_data["rules_and_lessons"] and context_data["rules_and_lessons"].strip():
            prompt_parts.append(f"{context_data['rules_and_lessons']}\n")

        # Build timezone-aware time context
        agent_timezone = getattr(agent, "timezone", "UTC") or "UTC"
        time_context = build_time_context_for_agent(agent_timezone, agent.business_hours or {})

        date_time_context = self._format_time_context(time_context)
        prompt_parts.append(date_time_context)

        # Add business details
        prompt_parts.append(f"BUSINESS DETAILS:\n{context_data['business']}\n")

        # Add general agent memories
        if context_data["memories"] and context_data["memories"].strip():
            prompt_parts.append(f"{context_data['memories']}\n")

        # Add context components that have content - PRIORITIZE appointments over menu
        context_sections = [
            ("appointments", context_data["appointments"]),  # Moved appointments FIRST
            ("menu", context_data["menu"]),
            ("current_conversation", context_data["current_conversation"]),
            ("historical_conversations", context_data["historical_conversations"]),
            ("historical_orders", context_data["historical_orders"]),
        ]

        for section_name, content in context_sections:
            if content and content.strip():
                prompt_parts.append(f"{content}\n")

        # Add service instructions
        service_instructions = self._build_service_instructions(agent)
        prompt_parts.append(service_instructions)

        return "\n".join(prompt_parts)

    def _format_time_context(self, time_context: Dict) -> str:
        """Format time context into readable string"""
        business_status = time_context["business_status"]

        context = f"""CURRENT DATE & TIME:
{time_context["current_datetime"]}
Current Time: {time_context["current_time"]}
Timezone: {time_context["timezone"]}

BUSINESS STATUS:
Currently: {"OPEN" if business_status["is_open"] else "CLOSED"}
Today's Hours: {business_status["today_hours"]["open"]}-{business_status["today_hours"]["close"]} ({"Enabled" if business_status["today_hours"]["enabled"] else "Closed"})"""

        # Add next opening time if closed
        if not business_status["is_open"] and "next_opening" in business_status:
            context += f"\nNext Opening: {business_status['next_opening']}"

        return f"{context}\n"

    def _build_service_instructions(self, agent: Agent) -> str:
        """Build service instructions based on enabled features"""
        instructions = [
            "Use this context to provide personalized, informed service.",
            "Reference previous interactions naturally when relevant.",
            "Be aware of current business hours and inform customers accordingly.",
        ]

        # Determine agent capabilities (mutually exclusive)
        ordering_enabled = getattr(agent, 'ordering_enabled', False)
        booking_enabled = getattr(agent, 'booking_enabled', False)

        # Ensure mutual exclusivity - if both are true, default to booking
        if ordering_enabled and booking_enabled:
            ordering_enabled = False
            booking_enabled = True

        if booking_enabled:
            instructions.append("For appointment requests, always check availability first, then book accordingly.")

        if ordering_enabled:
            instructions.append("For orders, use the menu items and existing order tools.")

        return " ".join(instructions)

    def _build_greeting(self, agent: Agent) -> str:
        """Build greeting message"""
        if agent.greeting and agent.greeting.strip() != "Hello! How can I help you today?":
            return agent.greeting
        return f"Hello! I'm {agent.name}. How can I help you today?"

    def _build_fallback_config(self, agent: Agent) -> Dict[str, Any]:
        """Build minimal fallback configuration to prevent call drops"""
        return {
            "agent": {
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": agent.voice_model or "aura-2-thalia-en",
                    }
                },
                "language": agent.language or "en",
                "think": {
                    "prompt": agent.system_prompt or "You are a helpful AI assistant.",
                    "functions": [],
                },
                "greeting": agent.greeting or "Hello! How can I help you today?",
            }
        }

    def _extract_functions_from_registry(self, agent: Agent = None) -> list:
        """Extract function definitions from the tools registry based on agent capabilities"""
        try:
            functions = []

            # Determine agent capabilities (mutually exclusive)
            ordering_enabled = getattr(agent, 'ordering_enabled', False) if agent else False
            booking_enabled = getattr(agent, 'booking_enabled', False) if agent else False

            # Ensure mutual exclusivity - if both are true, default to booking
            if ordering_enabled and booking_enabled:
                ordering_enabled = False
                booking_enabled = True

            # Define tool categories
            order_tools = {
                'add_order_item', 'remove_order_item', 'update_order_item',
                'get_order_summary', 'finalize_order', 'cancel_order',
                'get_menu_item', 'find_customer_orders'
            }

            appointment_tools = {
                'create_appointment', 'get_available_times', 'cancel_appointment',
                'reschedule_appointment', 'get_upcoming_appointments', 'add_attendee_to_appointment'
            }

            # Get all registered tools from the global registry
            for tool_name, tool_description in global_registry.tool_descriptions.items():
                tool_function_name = tool_description["name"]

                # Filter tools based on agent capabilities
                should_include_tool = True

                if tool_function_name in order_tools and not ordering_enabled:
                    should_include_tool = False
                    app_logger.info(f"[REGISTRY] Excluding order tool: {tool_function_name} (ordering disabled)")

                elif tool_function_name in appointment_tools and not booking_enabled:
                    should_include_tool = False
                    app_logger.info(f"[REGISTRY] Excluding appointment tool: {tool_function_name} (booking disabled)")

                if should_include_tool:
                    # Convert registry format to Deepgram Agent API format
                    function_def = {
                        "name": tool_description["name"],
                        "description": tool_description["description"] or f"Execute {tool_name} function",
                        "parameters": tool_description.get(
                            "parameters",
                            {"type": "object", "properties": {}, "required": []},
                        ),
                    }
                    functions.append(function_def)
                    app_logger.info(f"[REGISTRY] Included function: {function_def['name']}")

            capability_type = "booking" if booking_enabled else ("ordering" if ordering_enabled else "general")
            app_logger.info(f"Extracted {len(functions)} functions for {capability_type} agent: {[f['name'] for f in functions]}")
            return functions

        except Exception as e:
            app_logger.error(f"Error extracting functions from registry: {str(e)}")
            return []
