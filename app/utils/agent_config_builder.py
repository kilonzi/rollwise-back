from datetime import datetime
from typing import Dict, Any

from app.config.agent_constants import (
    PROMPT_TEMPLATE,
    SETTINGS,
    FUNCTION_DEFINITIONS,
)
from app.models import Agent


class AgentConfigBuilder:
    """Build agent configurations dynamically from database records"""

    @staticmethod
    def build_voice_settings(agent: Agent) -> Dict[str, Any]:
        """
        Build voice provider settings based on agent configuration

        Args:
            agent: Agent database object with voice configuration

        Returns:
            Voice settings dictionary for the configured provider
        """
        voice_model = agent.voice_model or "aura-2-thalia-en"
        return {
            "provider": {
                "type": "deepgram",
                "model": voice_model
            }
        }

    @staticmethod
    def get_voice_name_from_model(voice_model: str) -> str:
        """Extract a voice name from the model string"""
        try:
            # Handle format like "aura-2-thalia-en"
            parts = voice_model.split("-")
            if len(parts) >= 3:
                return parts[2].capitalize()
            return "Assistant"
        except Exception:
            return "Assistant"

    @staticmethod
    def build_personality_prompt(agent: Agent, voice_name: str) -> str:
        """Build personality section from agent data with reasonable defaults"""
        try:
            company_name = agent.tenant.name if (agent.tenant and hasattr(agent.tenant, 'name')) else "the business"
            business_type = getattr(agent.tenant, 'business_type', None) if agent.tenant else None
        except AttributeError:
            company_name = "the business"
            business_type = None

        # Use system_prompt from database if available, otherwise create default
        if agent.system_prompt and agent.system_prompt.strip() != "You are a helpful AI assistant.":
            # Agent has custom system prompt
            personality = agent.system_prompt
        else:
            # Create default personality based on business type
            if business_type:
                personality = f"You are {agent.name}, a friendly and professional representative for {company_name}, a {business_type}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
            else:
                personality = f"You are {agent.name}, a friendly and professional representative for {company_name}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."

        return personality

    @staticmethod
    def build_greeting_message(agent: Agent, voice_name: str) -> str:
        """Build greeting message from agent data with reasonable defaults"""
        if agent.greeting and agent.greeting.strip() != "Hello! How can I help you today?":
            return agent.greeting
        else:
            try:
                company_name = agent.tenant.name if (agent.tenant and hasattr(agent.tenant, 'name')) else "the business"
            except AttributeError:
                company_name = "the business"
            return f"Hello! I'm {agent.name} from {company_name}. How can I help you today?"

    @staticmethod
    def build_calendar_info(agent: Agent) -> str:
        """Build calendar information section for agent prompt"""
        if not agent.booking_enabled:
            return "\n\nCALENDAR BOOKING:\nBooking and appointments are not allowed at the moment. Please inform customers that appointment scheduling is currently unavailable."

        calendar_info = "\n\nCALENDAR BOOKING INFORMATION:"

        # Business hours
        if agent.business_hours:
            days_map = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday",
                        7: "Sunday"}
            business_days = [days_map.get(day, str(day)) for day in agent.business_hours.get("days", [1, 2, 3, 4, 5])]
            start_time = agent.business_hours.get("start", "09:00")
            end_time = agent.business_hours.get("end", "17:00")
            timezone = agent.business_hours.get("timezone", "UTC")

            calendar_info += f"\n- Business Hours: {', '.join(business_days)} from {start_time} to {end_time} ({timezone})"

        # Slot duration
        if agent.default_slot_duration:
            calendar_info += f"\n- Default appointment duration: {agent.default_slot_duration} minutes"

        # Buffer time
        if agent.buffer_time:
            calendar_info += f"\n- Buffer time between appointments: {agent.buffer_time} minutes"

        # Overbooking policy
        if agent.max_slot_appointments:
            if agent.max_slot_appointments == 1:
                calendar_info += "\n- Overbooking policy: No overlapping appointments allowed (maximum 1 appointment per time slot)"
            else:
                calendar_info += f"\n- Overbooking policy: Maximum {agent.max_slot_appointments} appointments per time slot"

        # Blocked dates
        if agent.blocked_dates:
            blocked_dates_str = ", ".join(agent.blocked_dates)
            calendar_info += f"\n- Unavailable dates: {blocked_dates_str}"

        # Calendar ID (for reference)
        if agent.calendar_id:
            calendar_info += f"\n- Calendar ID: {agent.calendar_id}"

        calendar_info += "\n\nWhen customers request appointments, use the calendar tools to check availability and create bookings within business hours only."

        return calendar_info

    @staticmethod
    def build_agent_config(agent: Agent, customer_context: str = "", collection_details: str = "") -> Dict[str, Any]:
        """
        Build complete agent configuration from database record with comprehensive context

        Args:
            agent: Agent database object with tenant relationship loaded
            customer_context: Customer history and context information
            collection_details: Available collections and knowledge base information

        Returns:
            Complete agent configuration dictionary ready for voice agent
        """
        # Extract basic info
        voice_model = agent.voice_model or "aura-2-thalia-en"
        voice_name = AgentConfigBuilder.get_voice_name_from_model(voice_model)
        language = agent.language or "en"

        # Build greeting from agent data
        greeting = AgentConfigBuilder.build_greeting_message(agent, voice_name)

        # Format the general prompt template with current date
        formatted_general_prompt = PROMPT_TEMPLATE.format(
            current_date=datetime.now().strftime("%A, %B %d, %Y")
        )

        # Build calendar information section
        calendar_info = AgentConfigBuilder.build_calendar_info(agent)

        # Build customer context section
        customer_context_section = ""
        if customer_context and customer_context.strip():
            customer_context_section = f"\n\nCUSTOMER CONTEXT:\n{customer_context}\n\nUse this customer history to provide personalized service. Reference previous interactions when relevant, but be natural about it. If the customer has specific preferences or past issues, keep them in mind during the conversation."

        # Build collection information section
        collection_section = ""
        if collection_details and collection_details.strip():
            collection_section = f"\n\n{collection_details}\n\nWhen customers ask questions about business information that might be in these collections, use the search_collection function with the appropriate collection name and query terms."

        # Combine agent's custom prompt (system_prompt) with all context sections
        if agent.system_prompt and agent.system_prompt.strip() and agent.system_prompt.strip() != "You are a helpful AI assistant.":
            # Use agent's custom prompt + general template + calendar info + customer context + collections
            full_prompt = agent.system_prompt + "\n\n" + formatted_general_prompt + calendar_info + customer_context_section + collection_section
        else:
            # Use general template with a simple default identity + all context sections
            try:
                company_name = agent.tenant.name if (agent.tenant and hasattr(agent.tenant, 'name')) else "the business"
                business_type = getattr(agent.tenant, 'business_type', None) if agent.tenant else None
            except AttributeError:
                # Fallback if tenant relationship is not loaded
                company_name = "the business"
                business_type = None

            if business_type:
                default_identity = f"You are {voice_name}, a friendly and professional representative for {company_name}, a {business_type}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
            else:
                default_identity = f"You are {voice_name}, a friendly and professional representative for {company_name}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."

            full_prompt = default_identity + "\n\n" + formatted_general_prompt + calendar_info + customer_context_section + collection_section

        # Create settings based on agent configuration
        agent_settings = SETTINGS.copy()

        # Update voice settings with ElevenLabs
        agent_settings["agent"]["speak"] = AgentConfigBuilder.build_voice_settings(agent)

        # Update language
        agent_settings["agent"]["language"] = language

        # Update prompt with combined content
        agent_settings["agent"]["think"]["prompt"] = full_prompt

        # Update greeting
        agent_settings["agent"]["greeting"] = greeting

        # Add function definitions (tools will be filtered based on agent.tools if needed)
        agent_settings["agent"]["think"]["functions"] = FUNCTION_DEFINITIONS
        return agent_settings

    @staticmethod
    def get_reasonable_defaults() -> Dict[str, Any]:
        """Get reasonable default values for missing agent data"""
        return {
            "voice_model": "aura-2-thalia-en",
            "language": "en",
            "greeting": "Hello! How can I help you today?",
            "system_prompt": "You are a helpful and professional customer service representative.",
        }

    @staticmethod
    def format_collections_prompt(collections: list[dict]) -> str:
        """
        Format a prompt section listing all collections for the agent, including name, description, and rules.
        Args:
            collections: List of dicts with keys: collection_name, display_name, description, notes/rules.
        Returns:
            A formatted string for use in LLM system prompts.
        """
        if not collections:
            return "No collections available."
        prompt = f"You have been provided with {len(collections)} collections. These collections are your only sources of truth.\nDo not rely on external information. Do not hallucinate.\n\nHere are the collections:\n"
        for idx, col in enumerate(collections, 1):
            name = col.get("collection_name") or col.get("display_name") or f"Collection {idx}"
            desc = col.get("description", "No description provided.")
            rules = col.get("notes") or col.get("rules") or "No rules provided."
            prompt += f"{idx}. {name} — Purpose: {desc}. Key rules: {rules}.\n"
        prompt += ("\nWhen answering a user query:\n"
                   "- Select the most relevant collection(s).\n"
                   "- Call `search_collection(collection_name, query, k=50)` to retrieve results.\n"
                   "- Read the retrieved snippets carefully.\n"
                   "- Answer strictly based on retrieved content.\n"
                   "- If snippets do not contain the answer, say \"I don’t know.\"\n")
        return prompt
