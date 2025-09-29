"""
Common utilities for context building
"""

from typing import Optional, Callable, Any
from sqlalchemy.orm import Session

from app.models import Order
from app.utils.logging_config import app_logger


def safe_execute(operation: Callable, error_message: str, fallback: Any = None) -> Any:
    """Safely execute an operation with error handling"""
    try:
        return operation()
    except Exception as e:
        app_logger.error(f"{error_message}: {str(e)}")
        return fallback


def get_phone_from_conversation(db_session: Session, conversation_id: str) -> Optional[str]:
    """Extract phone number from conversation record"""
    def _get_phone():
        from app.models import Conversation
        conversation = (
            db_session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        return conversation.caller_phone if conversation else None

    return safe_execute(
        _get_phone,
        "Error getting phone from conversation",
        None
    )


def get_current_order_id(db_session: Session, conversation_id: str) -> Optional[str]:
    """Get current order ID associated with the conversation"""
    def _get_order_id():
        order = (
            db_session.query(Order)
            .filter(Order.conversation_id == conversation_id)
            .first()
        )
        return order.id if order else None

    return safe_execute(
        _get_order_id,
        "Error getting current order ID",
        None
    )
