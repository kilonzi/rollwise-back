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

    # API Keys
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Google Cloud Configuration
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")

    # Voice Configuration
    VOICE: str = os.getenv("VOICE", "aura-2-thalia-en")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./calls.db")

    # Audio Processing
    BUFFER_SIZE: int = int(os.getenv("BUFFER_SIZE", str(20 * 160)))  # 20ms @ 8kHz μ-law
    SILENCE_THRESHOLD: int = int(os.getenv("SILENCE_THRESHOLD", "200"))

    # Business Configuration
    BUSINESS_NAME: str = os.getenv("BUSINESS_NAME", "Your Business")

    # Validation - ensure required variables are set
    if not DEEPGRAM_API_KEY:
        print("⚠️  Warning: DEEPGRAM_API_KEY not set")

    if BASE_URL == "yourdomain.com":
        print("⚠️  Warning: BASE_URL not configured - update with your domain/ngrok URL")


settings = Settings()
