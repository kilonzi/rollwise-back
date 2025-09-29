"""
Menu context builder utility
"""

from sqlalchemy.orm import Session

from app.models import Agent, MenuItem
from app.utils.logging_config import app_logger
from app.utils.context_formatters import format_menu_item


def build_menu_context(db_session: Session, agent: Agent) -> str:
    """Build current menu items context"""
    if not getattr(agent, 'ordering_enabled', True):
        return ""

    try:
        menu_items = (
            db_session.query(MenuItem)
            .filter(
                MenuItem.agent_id == agent.id,
                MenuItem.active == True,
                MenuItem.available == True,
                MenuItem.is_hidden == False,
            )
            .order_by(MenuItem.category, MenuItem.name)
            .all()
        )

        if not menu_items:
            return "MENU: No items available"

        # Group by category
        categories = {}
        for item in menu_items:
            if item.category not in categories:
                categories[item.category] = []
            categories[item.category].append(item)

        menu_text = f"CURRENT MENU ({len(menu_items)} items):\n"

        for category, items in categories.items():
            menu_text += f"\n{category.upper()}:\n"
            for item in items:
                menu_text += format_menu_item(item)

        menu_text += "\nIMPORTANT: Only offer items from this menu. Never suggest unavailable items."
        return menu_text

    except Exception as e:
        app_logger.error(f"Error building menu context: {str(e)}")
        return "MENU: Temporarily unavailable"
