"""
Unified Context Builder Service

This service consolidates all agent configuration and context building logic,
including business details, menu items, conversation history, and order history.
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.config.agent_constants import PLATFORM_TEMPLATE
from app.models import Agent, Conversation, Order, MenuItem
from app.tools.registry import global_registry
from app.utils.logging_config import app_logger
from app.utils.timezone_utils import build_time_context_for_agent


class ContextBuilderService:
    """Service for building comprehensive agent context from all relevant data sources"""

    def __init__(self, db_session: Session):
        self.db_session = db_session

    def build_complete_agent_config(
        self,
        agent: Agent,
        phone_number: str = None,
        conversation_id: str = None,
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
            # 1. Get business details
            business_context = self._build_business_context(agent)

            # 2. Get current menu items
            menu_context = self._build_menu_context(agent)

            # 3. Get current conversation context (includes current order if exists)
            current_conversation_context = ""
            if conversation_id:
                current_conversation_context = self._build_current_conversation_context(
                    conversation_id
                )
                # Extract phone number from current conversation if not provided
                if not phone_number:
                    phone_number = self._get_phone_from_conversation(conversation_id)

            # 4. Get historical conversation context (last 3, excluding current)
            historical_conversation_context = ""
            if phone_number:
                historical_conversation_context = (
                    self._build_historical_conversation_context(
                        agent.id,
                        phone_number,
                        lookback_days,
                        exclude_conversation_id=conversation_id,
                        limit=3,
                    )
                )

            # 5. Get historical order context (last 3, excluding current if it exists)
            historical_order_context = ""
            if phone_number:
                current_order_id = (
                    self._get_current_order_id(conversation_id)
                    if conversation_id
                    else None
                )
                historical_order_context = self._build_historical_order_context(
                    agent.id,
                    phone_number,
                    lookback_days,
                    exclude_order_id=current_order_id,
                    limit=3,
                )

            # 6. Build the complete system prompt
            system_prompt = self._build_unified_system_prompt(
                agent=agent,
                business_context=business_context,
                menu_context=menu_context,
                current_conversation_context=current_conversation_context,
                historical_conversation_context=historical_conversation_context,
                historical_order_context=historical_order_context,
            )

            # 7. Build complete agent configuration using official Deepgram Agent API format
            return {
                "type": "Settings",
                "audio": {
                    "input": {"encoding": "mulaw", "sample_rate": 8000},
                    "output": {
                        "encoding": "mulaw",
                        "sample_rate": 8000,
                        "container": "none",
                    },
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
                        "functions": self._extract_functions_from_registry(),
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

    def _build_business_context(self, agent: Agent) -> str:
        """Build business details context"""
        context_parts = []

        # Business name and type
        try:
            business_name = agent.tenant.name if agent.tenant else "the business"
            business_type = (
                getattr(agent.tenant, "business_type", None) if agent.tenant else None
            )

            if business_type:
                context_parts.append(f"Business: {business_name} ({business_type})")
            else:
                context_parts.append(f"Business: {business_name}")
        except AttributeError:
            context_parts.append("Business: the business")

        # Business hours
        if agent.business_hours:
            days_map = {
                1: "Monday",
                2: "Tuesday",
                3: "Wednesday",
                4: "Thursday",
                5: "Friday",
                6: "Saturday",
                7: "Sunday",
            }
            business_days = [
                days_map.get(day, str(day))
                for day in agent.business_hours.get("days", [1, 2, 3, 4, 5])
            ]
            start_time = agent.business_hours.get("start", "09:00")
            end_time = agent.business_hours.get("end", "17:00")
            timezone = agent.business_hours.get("timezone", "UTC")

            context_parts.append(
                f"Hours: {', '.join(business_days)} {start_time}-{end_time} ({timezone})"
            )

        # Booking settings
        if agent.booking_enabled:
            booking_details = []
            if agent.default_slot_duration:
                booking_details.append(f"{agent.default_slot_duration}min appointments")
            if agent.buffer_time:
                booking_details.append(f"{agent.buffer_time}min buffer")
            if agent.max_slot_appointments:
                if agent.max_slot_appointments == 1:
                    booking_details.append("no overlapping appointments")
                else:
                    booking_details.append(
                        f"max {agent.max_slot_appointments} per slot"
                    )

            if booking_details:
                context_parts.append(f"Booking: {', '.join(booking_details)}")
        else:
            context_parts.append("Booking: disabled")

        # Blocked dates
        if agent.blocked_dates:
            context_parts.append(f"Unavailable: {', '.join(agent.blocked_dates)}")

        return " | ".join(context_parts)

    def _build_menu_context(self, agent: Agent) -> str:
        """Build current menu items context"""
        try:
            menu_items = (
                self.db_session.query(MenuItem)
                .filter(
                    MenuItem.agent_id == agent.id,
                    MenuItem.active == True,
                    MenuItem.available == True,
                    MenuItem.is_hidden == False,
                )
                .order_by(MenuItem.category, MenuItem.name)
                .all()
            )

            if not menu_items:
                return "MENU: No items available"

            # Group by category
            categories = {}
            for item in menu_items:
                if item.category not in categories:
                    categories[item.category] = []
                categories[item.category].append(item)

            menu_text = f"CURRENT MENU ({len(menu_items)} items):\n"

            for category, items in categories.items():
                menu_text += f"\n{category.upper()}:\n"
                for item in items:
                    menu_text += (
                        f"• Item Id: {item.id} - {item.name} - ${item.price:.2f}"
                    )
                    if item.number:
                        menu_text += f" (#{item.number})"

                    # Add special indicators
                    indicators = []
                    if item.is_popular:
                        indicators.append("POPULAR")
                    if item.is_special:
                        indicators.append("SPECIAL")
                    if item.is_new:
                        indicators.append("NEW")
                    if item.is_limited_time:
                        indicators.append("LIMITED")

                    if indicators:
                        menu_text += f" [{', '.join(indicators)}]"

                    menu_text += "\n"

                    if item.description:
                        menu_text += f"  {item.description}\n"

            menu_text += "\nIMPORTANT: Only offer items from this menu. Never suggest unavailable items."
            return menu_text

        except Exception as e:
            app_logger.error(f"Error building menu context: {str(e)}")
            return "MENU: Temporarily unavailable"

    def _build_conversation_history_context(
        self, agent_id: str, phone_number: str, lookback_days: int, limit: int = 3
    ) -> str:
        """Build last N conversations context"""
        try:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            conversations = (
                self.db_session.query(Conversation)
                .filter(
                    and_(
                        Conversation.agent_id == agent_id,
                        Conversation.caller_phone == phone_number,
                        Conversation.created_at >= cutoff_date,
                        Conversation.summary.isnot(None),
                        Conversation.summary != "",
                    )
                )
                .order_by(desc(Conversation.created_at))
                .limit(limit)
                .all()
            )

            if not conversations:
                return "CONVERSATION HISTORY: New customer - no previous calls"

            history_text = f"CONVERSATION HISTORY (last {len(conversations)} calls):\n"

            for i, conv in enumerate(conversations, 1):
                days_ago = (datetime.now() - conv.created_at).days
                time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

                history_text += f"{i}. {time_desc}: {conv.summary}\n"
                if conv.conversation_type:
                    history_text += f"   Type: {conv.conversation_type}\n"

            return history_text

        except Exception as e:
            app_logger.error(f"Error building conversation history: {str(e)}")
            return "CONVERSATION HISTORY: Error retrieving history"

    def _build_order_history_context(
        self, agent_id: str, phone_number: str, lookback_days: int, limit: int = 3
    ) -> str:
        """Build last N orders context"""
        try:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            orders = (
                self.db_session.query(Order)
                .filter(
                    and_(
                        Order.agent_id == agent_id,
                        Order.customer_phone == phone_number,
                        Order.created_at >= cutoff_date,
                        Order.active == True,
                    )
                )
                .order_by(desc(Order.created_at))
                .limit(limit)
                .all()
            )

            if not orders:
                return "ORDER HISTORY: No previous orders"

            history_text = f"ORDER HISTORY (last {len(orders)} orders):\n"

            for i, order in enumerate(orders, 1):
                days_ago = (datetime.now() - order.created_at).days
                time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

                history_text += (
                    f"{i}. {time_desc} - ${order.total_price:.2f} ({order.status})\n"
                )

                # Add order items
                if order.order_items:
                    for item in order.order_items[:3]:  # Show max 3 items
                        history_text += (
                            f"   • {item.quantity}x {item.name} @ ${item.price:.2f}\n"
                        )

                    if len(order.order_items) > 3:
                        history_text += (
                            f"   ... and {len(order.order_items) - 3} more items\n"
                        )

            return history_text

        except Exception as e:
            app_logger.error(f"Error building order history: {str(e)}")
            return "ORDER HISTORY: Error retrieving order history"

    def _build_unified_system_prompt(
        self,
        agent: Agent,
        business_context: str,
        menu_context: str,
        current_conversation_context: str,
        historical_conversation_context: str,
        historical_order_context: str,
    ) -> str:
        """Build the complete unified system prompt"""

        # Use centralized platform template for consistent tone and behavior
        platform_prompt = PLATFORM_TEMPLATE

        # Agent's custom prompt (if available)
        agent_prompt = ""
        if (
            agent.system_prompt
            and agent.system_prompt.strip() != "You are a helpful AI assistant."
        ):
            agent_prompt = f"AGENT PERSONALITY:\n{agent.system_prompt}\n\n"

        # Build timezone-aware time context
        agent_timezone = getattr(agent, "timezone", "UTC") or "UTC"
        time_context = build_time_context_for_agent(
            agent_timezone, agent.business_hours or {}
        )

        # Enhanced date and time context with business status
        date_time_context = f"""CURRENT DATE & TIME:
{time_context["current_datetime"]}
Current Time: {time_context["current_time"]}
Timezone: {time_context["timezone"]}

BUSINESS STATUS:
Currently: {"OPEN" if time_context["business_status"]["is_open"] else "CLOSED"}
Today's Hours: {time_context["business_status"]["today_hours"]["open"]}-{time_context["business_status"]["today_hours"]["close"]} ({"Enabled" if time_context["business_status"]["today_hours"]["enabled"] else "Closed"})"""

        # Add next opening time if closed
        if (
            not time_context["business_status"]["is_open"]
            and "next_opening" in time_context["business_status"]
        ):
            date_time_context += (
                f"\nNext Opening: {time_context['business_status']['next_opening']}"
            )

        date_time_context += "\n\n"

        # Build complete prompt
        complete_prompt = (
            platform_prompt
            + agent_prompt
            + date_time_context
            + f"BUSINESS DETAILS:\n{business_context}\n\n"
            + f"{menu_context}\n\n"
            + f"{current_conversation_context}\n\n"
            + f"{historical_conversation_context}\n\n"
            + f"{historical_order_context}\n\n"
            + "Use this context to provide personalized, informed service. "
            "Reference previous interactions and orders naturally when relevant. "
            "Be aware of current business hours and inform customers accordingly."
        )

        return complete_prompt

    def _build_voice_config(self, agent: Agent) -> Dict[str, Any]:
        """Build voice provider configuration"""
        return {
            "provider": {
                "type": "deepgram",
                "model": agent.voice_model or "aura-2-thalia-en",
            }
        }

    def _build_greeting(self, agent: Agent) -> str:
        """Build greeting message"""
        if (
            agent.greeting
            and agent.greeting.strip() != "Hello! How can I help you today?"
        ):
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

    def _build_current_conversation_context(self, conversation_id: str) -> str:
        """Build current conversation context (includes current order if exists)"""
        try:
            conversation = (
                self.db_session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )

            if not conversation:
                return "No current conversation context available"

            # Basic conversation info
            context_parts = [
                "CURRENT CONVERSATION:",
                f"- Conversation ID: {conversation.id}",
                f"- The Customer Phone Number is (don't ask for it), use this one: {conversation.caller_phone}",
            ]

            # Find the order associated with this conversation
            order = (
                self.db_session.query(Order)
                .filter(Order.conversation_id == conversation.id)
                .first()
            )

            if order:
                context_parts.extend(
                    [
                        "",
                        "CURRENT ORDER (ALWAYS USE THIS ORDER):",
                        f"- Order ID: {order.id}",
                        f"- Customer Phone Number: {order.customer_phone}",
                    ]
                )

                # Add current order items
                if order.order_items:
                    context_parts.append("- Current Items:")
                    for item in order.order_items:
                        context_parts.append(f"  • {item.quantity}x {item.name}")
                        if item.note:
                            context_parts.append(f"    Note: {item.note}")
                else:
                    context_parts.append("- Current Items: None (empty order)")

                context_parts.extend(
                    [
                        "",
                        "IMPORTANT ORDER INSTRUCTIONS:",
                        f"- ALWAYS use Order ID {order.id} for all order operations",
                        "- NEVER create a new order during this conversation",
                        "- Add/modify/remove items using the existing order tools",
                        "- This order already exists and is ready for items",
                        " -You must always call finalize_order, this is the only way it's useful",
                        " - You must always get the customer's name for the order",
                    ]
                )
            else:
                context_parts.extend(
                    [
                        "",
                        "ORDER STATUS:",
                        "- No order found for this conversation",
                        "- An order should have been created automatically",
                        "- Check with order management if needed",
                    ]
                )

            return "\n".join(context_parts)

        except Exception as e:
            app_logger.error(f"Error building current conversation context: {str(e)}")
            return "Error retrieving current conversation context"

    def _get_phone_from_conversation(self, conversation_id: str) -> str:
        """Extract phone number from conversation record"""
        try:
            conversation = (
                self.db_session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            return conversation.caller_phone if conversation else None
        except Exception as e:
            app_logger.error(f"Error getting phone from conversation: {str(e)}")
            return None

    def _get_current_order_id(self, conversation_id: str) -> str:
        """Get current order ID associated with the conversation"""
        try:
            order = (
                self.db_session.query(Order)
                .filter(Order.conversation_id == conversation_id)
                .first()
            )
            return order.id if order else None
        except Exception as e:
            app_logger.error(f"Error getting current order ID: {str(e)}")
            return None

    def _build_historical_conversation_context(
        self,
        agent_id: str,
        phone_number: str,
        lookback_days: int,
        exclude_conversation_id: str = None,
        limit: int = 3,
    ) -> str:
        """Build historical conversation context, excluding current conversation"""
        try:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            query = (
                self.db_session.query(Conversation)
                .filter(
                    and_(
                        Conversation.agent_id == agent_id,
                        Conversation.caller_phone == phone_number,
                        Conversation.created_at >= cutoff_date,
                        Conversation.summary.isnot(None),
                        Conversation.summary != "",
                    )
                )
                .order_by(desc(Conversation.created_at))
            )

            # Exclude the current conversation if ID is provided
            if exclude_conversation_id:
                query = query.filter(Conversation.id != exclude_conversation_id)

            conversations = query.limit(limit).all()

            if not conversations:
                return "No historical conversation context available"

            history_text = f"HISTORICAL CONVERSATIONS/INCLUDING A PREVIOUS CUSTOMER NAME (last {len(conversations)}):\n"

            for i, conv in enumerate(conversations, 1):
                days_ago = (datetime.now() - conv.created_at).days
                time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

                history_text += f"{i}. {time_desc}: {conv.summary}\n"
                if conv.conversation_type:
                    history_text += f"   Type: {conv.conversation_type}\n"

            return history_text

        except Exception as e:
            app_logger.error(
                f"Error building historical conversation context: {str(e)}"
            )
            return "Error retrieving historical conversation context"

    def _build_historical_order_context(
        self,
        agent_id: str,
        phone_number: str,
        lookback_days: int,
        exclude_order_id: str = None,
        limit: int = 3,
    ) -> str:
        """Build historical order context, excluding current order if it exists"""
        try:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)

            query = (
                self.db_session.query(Order)
                .filter(
                    and_(
                        Order.agent_id == agent_id,
                        Order.customer_phone == phone_number,
                        Order.created_at >= cutoff_date,
                        Order.active == True,
                    )
                )
                .order_by(desc(Order.created_at))
            )

            # Exclude the current order if ID is provided
            if exclude_order_id:
                query = query.filter(Order.id != exclude_order_id)

            orders = query.limit(limit).all()

            if not orders:
                return "ORDER HISTORY: No previous orders"

            history_text = f"ORDER HISTORY (last {len(orders)} orders):\n"

            for i, order in enumerate(orders, 1):
                days_ago = (datetime.now() - order.created_at).days
                time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

                history_text += (
                    f"{i}. {time_desc} - ${order.total_price:.2f} ({order.status})\n"
                )

                # Add order items
                if order.order_items:
                    for item in order.order_items[:3]:  # Show max 3 items
                        history_text += (
                            f"   • {item.quantity}x {item.name} @ ${item.price:.2f}\n"
                        )

                    if len(order.order_items) > 3:
                        history_text += (
                            f"   ... and {len(order.order_items) - 3} more items\n"
                        )

            return history_text

        except Exception as e:
            app_logger.error(f"Error building order history: {str(e)}")
            return "ORDER HISTORY: Error retrieving order history"

    def _extract_functions_from_registry(self) -> list:
        """Extract function definitions from the tools registry to avoid duplication"""
        try:
            functions = []

            # Get all registered tools from the global registry
            for (
                tool_name,
                tool_description,
            ) in global_registry.tool_descriptions.items():
                # Convert registry format to Deepgram Agent API format
                function_def = {
                    "name": tool_description["name"],
                    "description": tool_description["description"]
                    or f"Execute {tool_name} function",
                    "parameters": tool_description.get(
                        "parameters",
                        {"type": "object", "properties": {}, "required": []},
                    ),
                }
                functions.append(function_def)
                app_logger.info(
                    f"[REGISTRY] Extracted function: {function_def['name']}"
                )

            app_logger.info(
                f"Extracted {len(functions)} functions from registry: {[f['name'] for f in functions]}"
            )
            return functions

        except Exception as e:
            app_logger.error(f"Error extracting functions from registry: {str(e)}")
            return []
