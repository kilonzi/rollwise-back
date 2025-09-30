import asyncio
from app.models import get_db
from app.services.conversation_service import ConversationService
from app.utils.logging_config import app_logger as logger

async def run_stale_conversation_cleanup():
    """
    Periodically runs the cleanup process for stale conversations.
    """
    while True:
        logger.info("Running scheduled cleanup of stale conversations...")
        db_session = next(get_db())
        try:
            conversation_service = ConversationService(db_session)
            await conversation_service.cleanup_stale_conversations(timeout_hours=1)
        except Exception as e:
            logger.error(f"An error occurred during the stale conversation cleanup job: {e}")
        finally:
            db_session.close()

        # Wait for 1 hour before running again
        await asyncio.sleep(3600)

