from datetime import datetime
from typing import Dict, Any

from app.models import Agent


class AgentConfigBuilder:
    """Build agent configurations dynamically from database records - Legacy support"""

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
        return {"provider": {"type": "deepgram", "model": voice_model}}

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
    def build_agent_config(
        agent: Agent,
        customer_context: str = "",
        collection_details: str = "",
        conversation_details: str = "",
    ) -> Dict[str, Any]:
        """
        Legacy method - Use ContextBuilderService.build_complete_agent_config() instead

        This method is kept for backward compatibility but should be replaced
        with the new unified ContextBuilderService approach.
        """
        # Simple fallback configuration
        voice_model = agent.voice_model or "aura-2-thalia-en"
        language = agent.language or "en"
        greeting = agent.greeting or "Hello! How can I help you today?"

        # Combine all context into system prompt
        system_prompt = agent.system_prompt or "You are a helpful AI assistant."

        if customer_context:
            system_prompt += f"\n\nCUSTOMER CONTEXT:\n{customer_context}"

        if collection_details:
            system_prompt += f"\n\nKNOWLEDGE BASE:\n{collection_details}"

        if conversation_details:
            system_prompt += f"\n\nCONVERSATION CONTEXT:\n{conversation_details}"

        return {
            "agent": {
                "speak": AgentConfigBuilder.build_voice_settings(agent),
                "language": language,
                "think": {
                    "prompt": system_prompt,
                    "functions": [],  # Will be populated by tools registry
                },
                "greeting": greeting,
            }
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
            name = (
                col.get("collection_name")
                or col.get("display_name")
                or f"Collection {idx}"
            )
            desc = col.get("description", "No description provided.")
            rules = col.get("notes") or col.get("rules") or "No rules provided."
            prompt += f"{idx}. {name} — Purpose: {desc}. Key rules: {rules}.\n"
        prompt += (
            "\nWhen answering a user query:\n"
            "- Select the most relevant collection(s).\n"
            "- Call `search_collection(collection_name, query, k=50)` to retrieve results.\n"
            "- Read the retrieved snippets carefully.\n"
            "- Answer strictly based on retrieved content.\n"
            '- If snippets do not contain the answer, say "I don\'t know."\n'
        )
        return prompt
