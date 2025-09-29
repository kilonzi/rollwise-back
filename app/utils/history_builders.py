"""
History context builder utilities
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.models import Conversation, Order
from app.utils.logging_config import app_logger
from app.utils.context_formatters import format_conversation_item, format_order_item


def build_historical_conversations(
    db_session: Session,
    agent_id: str,
    phone_number: str,
    lookback_days: int,
    exclude_conversation_id: Optional[str] = None,
    limit: int = 3,
) -> str:
    """Build historical conversation context"""
    try:
        cutoff_date = datetime.now() - timedelta(days=lookback_days)

        query = (
            db_session.query(Conversation)
            .filter(
                and_(
                    Conversation.agent_id == agent_id,
                    Conversation.caller_phone == phone_number,
                    Conversation.created_at >= cutoff_date,
                    Conversation.summary.isnot(None),
                    Conversation.summary != "",
                )
            )
            .order_by(desc(Conversation.created_at))
        )

        if exclude_conversation_id:
            query = query.filter(Conversation.id != exclude_conversation_id)

        conversations = query.limit(limit).all()

        if not conversations:
            return "No historical conversation context available"

        history_text = f"HISTORICAL CONVERSATIONS (last {len(conversations)}):\n"
        for i, conv in enumerate(conversations, 1):
            history_text += format_conversation_item(conv, i)

        return history_text

    except Exception as e:
        app_logger.error(f"Error building historical conversation context: {str(e)}")
        return "Error retrieving historical conversation context"


def build_historical_orders(
    db_session: Session,
    agent_id: str,
    phone_number: str,
    lookback_days: int,
    exclude_order_id: Optional[str] = None,
    limit: int = 3,
) -> str:
    """Build historical order context"""
    try:
        cutoff_date = datetime.now() - timedelta(days=lookback_days)

        query = (
            db_session.query(Order)
            .filter(
                and_(
                    Order.agent_id == agent_id,
                    Order.customer_phone == phone_number,
                    Order.created_at >= cutoff_date,
                    Order.active == True,
                )
            )
            .order_by(desc(Order.created_at))
        )

        if exclude_order_id:
            query = query.filter(Order.id != exclude_order_id)

        orders = query.limit(limit).all()

        if not orders:
            return "ORDER HISTORY: No previous orders"

        history_text = f"ORDER HISTORY (last {len(orders)} orders):\n"
        for i, order in enumerate(orders, 1):
            history_text += format_order_item(order, i)

        return history_text

    except Exception as e:
        app_logger.error(f"Error building order history: {str(e)}")
        return "ORDER HISTORY: Error retrieving order history"


def build_current_conversation_context(
    db_session: Session, conversation_id: str
) -> tuple[str, Optional[str]]:
    """Build current conversation context and extract phone number"""
    try:
        conversation = (
            db_session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if not conversation:
            return "No current conversation context available", None

        context_parts = [
            "CURRENT CONVERSATION:",
            f"- Conversation ID: {conversation.id}",
            f"- The Customer Phone Number is (don't ask for it), use this one: {conversation.caller_phone}",
        ]

        # Find associated order
        order = (
            db_session.query(Order)
            .filter(Order.conversation_id == conversation.id)
            .first()
        )

        if order:
            from app.utils.context_formatters import format_current_order_context
            context_parts.append("")
            context_parts.append(format_current_order_context(order))
        else:
            context_parts.extend([
                "",
                "ORDER STATUS:",
                "- No order found for this conversation",
                "- An order should have been created automatically",
                "- Check with order management if needed",
            ])

        return "\n".join(context_parts), str(conversation.caller_phone)

    except Exception as e:
        app_logger.error(f"Error building current conversation context: {str(e)}")
        return "Error retrieving current conversation context", None
