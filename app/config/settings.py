import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()


# Server Configuration


class Settings(BaseSettings):
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8090"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    # External URLs
    BASE_URL: str = os.getenv("BASE_URL", "yourdomain.com")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080"
    )

    # API Keys - Required
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ELEVEN_LABS_API_KEY: str = os.getenv("ELEVEN_LABS_API_KEY", "")

    # Google Calendar Integration
    GOOGLE_CALENDAR_CREDENTIALS_PATH: str = os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS_PATH", "./credentials.json"
    )
    GOOGLE_CALENDAR_DOMAIN: str = os.getenv("GOOGLE_CALENDAR_DOMAIN", "")

    # Google Cloud Configuration
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")
    GEMINI_LLM_MODEL: str = os.getenv("GEMINI_LLM_MODEL", "gemini-2.0-flash")

    # Voice Configuration
    VOICE: str = os.getenv("VOICE", "aura-2-thalia-en")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/rollwise",
    )

    # ChromaDB Cloud
    CHROMA_API_KEY: str = os.getenv("CHROMA_API_KEY", "")
    CHROMA_TENANT: str = os.getenv("CHROMA_TENANT", "")
    CHROMA_DATABASE: str = os.getenv("CHROMA_DATABASE", "")

    # Audio Processing
    BUFFER_SIZE: int = int(os.getenv("BUFFER_SIZE", str(20 * 160)))  # 20ms @ 8kHz μ-law
    SILENCE_THRESHOLD: int = int(os.getenv("SILENCE_THRESHOLD", "200"))

    # Business Configuration
    BUSINESS_NAME: str = os.getenv("BUSINESS_NAME", "Your Business")

    def __post_init__(self) -> None:
        """Validate required settings after initialization"""
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable is required for security")

        if not self.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is required for speech processing")

        if self.BASE_URL == "yourdomain.com":
            raise ValueError("BASE_URL must be configured with your domain/ngrok URL")

        # Validate SECRET_KEY strength
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")


settings = Settings()
