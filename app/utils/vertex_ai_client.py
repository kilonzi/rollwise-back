import atexit
import os
import tempfile
from typing import Optional

from google import genai
from google.auth import exceptions

from app.utils.logging_config import app_logger as logger


class VertexAIClient:
    """A client for interacting with Google's Generative AI models via Vertex AI."""

    _instance = None
    _client: Optional[genai.client.Client] = None
    _async_client = None
    _temp_creds_file_path: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VertexAIClient, cls).__new__(cls)
            cls._instance._client = None
            cls._instance._async_client = None
            cls._instance._temp_creds_file_path = None
            try:
                service_account_contents = os.getenv("SERVICE_ACCOUNT_CONTENTS")

                if service_account_contents:
                    try:
                        # Create a temporary file to store service account credentials for ADC
                        with tempfile.NamedTemporaryFile(
                                mode="w", delete=False, suffix=".json"
                        ) as temp_creds_file:
                            temp_creds_file.write(service_account_contents)
                            cls._instance._temp_creds_file_path = temp_creds_file.name

                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                            cls._instance._temp_creds_file_path
                        )
                        atexit.register(cls._instance.close)  # Register cleanup
                        logger.info(
                            "✅ GenAI client configured to use credentials from SERVICE_ACCOUNT_CONTENTS."
                        )
                    except Exception as e:
                        logger.error(
                            f"⚠️ Failed to write SERVICE_ACCOUNT_CONTENTS to temp file: {e}"
                        )
                        raise

                project_id = os.getenv("GCP_PROJECT")
                location = os.getenv("GCP_REGION", "us-central1")

                if project_id:
                    client = genai.Client(
                        vertexai=True, project=project_id, location=location
                    )
                    cls._instance._client = client
                    cls._instance._async_client = client.aio
                    logger.info(
                        f"✅ GenAI client initialized for project {project_id} in {location}."
                    )
                else:
                    logger.warning(
                        "⚠️ GCP_PROJECT not set. GenAI client not fully initialized."
                    )

            except exceptions.DefaultCredentialsError:
                logger.warning(
                    "⚠️ Google Cloud authentication failed. "
                    "Please configure Application Default Credentials (ADC) or set GOOGLE_APPLICATION_CREDENTIALS."
                )
            except Exception as e:
                logger.exception(f"Failed to initialize GenAI client: {e}")

        return cls._instance

    def get_async_client(self):
        """Returns the initialized async Generative AI client."""
        return self._async_client

    def close(self):
        """Closes the client and cleans up resources."""
        if self._client:
            self._client.close()
            logger.info("GenAI client closed.")

        if self._temp_creds_file_path:
            try:
                os.remove(self._temp_creds_file_path)
                logger.info(
                    f"Removed temporary credentials file: {self._temp_creds_file_path}"
                )
            except OSError as e:
                logger.error(f"Error removing temporary credentials file: {e}")
            self._temp_creds_file_path = None


def get_vertex_ai_client() -> VertexAIClient:
    """
    Provides a singleton instance of the VertexAIClient.
    """
    return VertexAIClient()
