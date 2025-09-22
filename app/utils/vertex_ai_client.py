import os
from typing import Optional

from google.auth import exceptions
from vertexai.generative_models import GenerativeModel

from app.utils.logging_config import app_logger as logger


class VertexAIClient:
    """A client for interacting with the Vertex AI Generative Models."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VertexAIClient, cls).__new__(cls)
            cls._instance.model = None
            try:
                if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                    # For local development with a service account
                    cls._instance.model = GenerativeModel("gemini-1.5-flash")
                    logger.info(
                        "✅ Vertex AI client initialized successfully using service account."
                    )
                else:
                    # For environments with Application Default Credentials (ADC)
                    # This will work in Cloud Run, Cloud Functions, etc.
                    import vertexai

                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
                    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
                    if project_id:
                        vertexai.init(project=project_id, location=location)
                        cls._instance.model = GenerativeModel("gemini-1.5-flash")
                        logger.info(
                            f"✅ Vertex AI client initialized for project {project_id} in {location}."
                        )
                    else:
                        logger.warning(
                            "⚠️ GOOGLE_CLOUD_PROJECT not set. Vertex AI client not initialized."
                        )

            except exceptions.DefaultCredentialsError:
                logger.warning(
                    "⚠️ Google Cloud authentication failed. "
                    "Please configure Application Default Credentials (ADC) or set GOOGLE_APPLICATION_CREDENTIALS."
                )
            except Exception as e:
                logger.exception(f"Failed to initialize Vertex AI client: {e}")

        return cls._instance

    def get_model(self) -> Optional[GenerativeModel]:
        """Returns the initialized GenerativeModel instance."""
        return self.model


def get_vertex_ai_client() -> VertexAIClient:
    """
    Provides a singleton instance of the VertexAIClient.
    """
    return VertexAIClient()
