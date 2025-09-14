from datetime import datetime
from app.config.agent_constants import (
    PROMPT_TEMPLATE,
    SETTINGS,
    VOICE_AGENT_URL,
    USER_AUDIO_SAMPLE_RATE,
    USER_AUDIO_SECS_PER_CHUNK,
    USER_AUDIO_SAMPLES_PER_CHUNK,
    AGENT_AUDIO_SAMPLE_RATE,
    AGENT_AUDIO_BYTES_PER_SEC
)


class AgentTemplates:
    PROMPT_TEMPLATE = PROMPT_TEMPLATE

    def __init__(
        self,
        industry="business_service",
        voiceModel="aura-2-thalia-en",
        voiceName="",
        company_name="Your Business",
    ):
        self.voiceName = voiceName
        self.voiceModel = voiceModel
        self.company = company_name
        self.personality = ""
        self.first_message = ""
        self.capabilities = ""

        self.industry = industry

        self.prompt = self.PROMPT_TEMPLATE.format(
            current_date=datetime.now().strftime("%A, %B %d, %Y")
        )

        self.voice_agent_url = VOICE_AGENT_URL
        self.settings = SETTINGS.copy()  # Make a copy to avoid modifying the original
        self.user_audio_sample_rate = USER_AUDIO_SAMPLE_RATE
        self.user_audio_secs_per_chunk = USER_AUDIO_SECS_PER_CHUNK
        self.user_audio_samples_per_chunk = USER_AUDIO_SAMPLES_PER_CHUNK
        self.agent_audio_sample_rate = AGENT_AUDIO_SAMPLE_RATE
        self.agent_audio_bytes_per_sec = AGENT_AUDIO_BYTES_PER_SEC

        # Industry-specific configuration
        match self.industry:
            case "business_service":
                self.business_service()
            case "healthcare":
                self.healthcare()
            case "retail":
                self.retail()
            case "salon":
                self.salon()
            case "restaurant":
                self.restaurant()
            case "tech_support":
                self.tech_support()

        # Generate voice name if not provided
        if not self.voiceName:
            self.voiceName = self.get_voice_name_from_model(self.voiceModel)

        # Create the greeting message
        self.first_message = f"Hello! I'm {self.voiceName} from {self.company}. {self.capabilities} How can I help you today?"

        # Update settings with configured values
        self.settings["agent"]["speak"]["provider"]["model"] = self.voiceModel
        self.settings["agent"]["think"]["prompt"] = self.personality + "\n\n" + self.prompt
        self.settings["agent"]["greeting"] = self.first_message

    def business_service(
        self, company="Your Business", agent_voice="aura-2-thalia-en", voiceName=""
    ):
        """General business service template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a friendly and professional customer service representative for {self.company}. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions."

        self.capabilities = "I can help you with information about our services, hours, pricing, and answer any questions you might have."

    def salon(
        self, company="Style Salon", agent_voice="aura-2-thalia-en", voiceName=""
    ):
        """Hair salon / beauty service template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a friendly and knowledgeable receptionist for {self.company}, a full-service hair salon. Your role is to assist clients with appointments, service information, pricing, and general salon inquiries."

        self.capabilities = "I can help you with appointment scheduling, service information, pricing, our hours, and any questions about our salon services."

    def restaurant(
        self, company="Bistro Restaurant", agent_voice="aura-2-andromeda-en", voiceName=""
    ):
        """Restaurant service template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a friendly and helpful host for {self.company}. Your role is to assist customers with reservations, menu information, hours, and general restaurant inquiries."

        self.capabilities = "I can help you with reservations, menu information, our hours, special events, and answer questions about our restaurant."

    def healthcare(
        self, company="HealthFirst Clinic", agent_voice="aura-2-andromeda-en", voiceName=""
    ):
        """Healthcare service template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a compassionate and professional medical receptionist for {self.company}, a healthcare provider. Your role is to assist patients with appointments, basic information, and general healthcare inquiries. You cannot provide medical advice."

        self.capabilities = "I can help you schedule appointments, provide information about our services and hours, and answer general questions about our clinic."

    def retail(self, company="StyleMart", agent_voice="aura-2-aries-en", voiceName=""):
        """Retail store template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a friendly and knowledgeable sales associate for {self.company}, a retail store. Your role is to assist customers with product information, inventory, store hours, and general shopping inquiries."

        self.capabilities = "I can help you find products, check availability, provide pricing information, and answer questions about our store."

    def tech_support(
        self, company="TechStyle", agent_voice="aura-2-apollo-en", voiceName=""
    ):
        """Tech support template"""
        if voiceName == "":
            voiceName = self.get_voice_name_from_model(agent_voice)
        self.voiceName = voiceName
        self.company = company
        self.voiceModel = agent_voice

        self.personality = f"You are {self.voiceName}, a knowledgeable and patient technical support representative for {self.company}, a technology company. Your role is to assist customers with technical inquiries, account information, and general support questions."

        self.capabilities = "I can help you with technical questions, account information, and provide support for our services."

    @staticmethod
    def get_available_industries():
        """Return a dictionary of available industries with display names"""
        return {
            "business_service": "General Business Service",
            "salon": "Hair Salon / Beauty Service",
            "restaurant": "Restaurant / Food Service",
            "healthcare": "Healthcare / Medical",
            "retail": "Retail / Shopping",
            "tech_support": "Technical Support",
        }

    def get_voice_name_from_model(self, model):
        """Extract a voice name from the model string"""
        try:
            # Handle format like "aura-2-thalia-en"
            parts = model.split("-")
            if len(parts) >= 3:
                return parts[2].capitalize()
            return "Assistant"
        except Exception:
            return "Assistant"

    def get_config_for_agent(self, agent):
        """Get the complete agent configuration"""
        # Update with agent-specific information
        if hasattr(agent, 'tenant') and agent.tenant:
            self.company = agent.tenant.name

        # Use agent's voice model if specified
        if hasattr(agent, 'voice_model') and agent.voice_model:
            self.voiceModel = agent.voice_model
            self.voiceName = self.get_voice_name_from_model(agent.voice_model)

        # Update greeting with agent-specific greeting if provided
        if hasattr(agent, 'greeting') and agent.greeting:
            custom_greeting = agent.greeting
        else:
            custom_greeting = self.first_message

        # Create final configuration
        final_settings = self.settings.copy()
        final_settings["agent"]["speak"]["provider"]["model"] = self.voiceModel
        final_settings["agent"]["think"]["prompt"] = self.personality + "\n\n" + self.prompt
        final_settings["agent"]["greeting"] = custom_greeting

        return final_settings