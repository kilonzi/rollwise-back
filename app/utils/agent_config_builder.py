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
        company_name = agent.tenant.name if agent.tenant else "the business"
        
        # Use system_prompt from database if available, otherwise create default
        if agent.system_prompt and agent.system_prompt.strip() != "You are a helpful AI assistant.":
            # Agent has custom system prompt
            personality = agent.system_prompt
        else:
            # Create default personality based on business type
            business_type = getattr(agent.tenant, 'business_type', None) if agent.tenant else None
            if business_type:
                personality = f"You are {voice_name}, a friendly and professional representative for {company_name}, a {business_type}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
            else:
                personality = f"You are {voice_name}, a friendly and professional representative for {company_name}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
        
        return personality
    
    @staticmethod
    def build_greeting_message(agent: Agent, voice_name: str) -> str:
        """Build greeting message from agent data with reasonable defaults"""
        if agent.greeting and agent.greeting.strip() != "Hello! How can I help you today?":
            return agent.greeting
        else:
            company_name = agent.tenant.name if agent.tenant else "the business"
            return f"Hello! I'm {voice_name} from {company_name}. How can I help you today?"
    
    
    @staticmethod
    def build_agent_config(agent: Agent) -> Dict[str, Any]:
        """
        Build complete agent configuration from database record
        
        Args:
            agent: Agent database object with tenant relationship loaded
            
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
        
        # Combine agent's custom prompt (system_prompt) with the general template
        if agent.system_prompt and agent.system_prompt.strip() and agent.system_prompt.strip() != "You are a helpful AI assistant.":
            # Use agent's custom prompt + general template
            full_prompt = agent.system_prompt + "\n\n" + formatted_general_prompt
        else:
            # Use general template with a simple default identity
            company_name = agent.tenant.name if agent.tenant else "the business"
            business_type = getattr(agent.tenant, 'business_type', None) if agent.tenant else None
            
            if business_type:
                default_identity = f"You are {voice_name}, a friendly and professional representative for {company_name}, a {business_type}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
            else:
                default_identity = f"You are {voice_name}, a friendly and professional representative for {company_name}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."
            
            full_prompt = default_identity + "\n\n" + formatted_general_prompt
        
        # Create settings based on agent configuration
        agent_settings = SETTINGS.copy()
        
        # Update voice model
        agent_settings["agent"]["speak"]["provider"]["model"] = voice_model
        
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