"""
MenuItemService for managing restaurant menu items
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime

from app.models import MenuItem, Agent
from app.api.schemas.menu_item import MenuItemCreate, MenuItemUpdate, MenuItemFilter
from app.utils.logging_config import app_logger


class MenuItemService:
    """Service for managing menu items"""

    @staticmethod
    def create_menu_item(db: Session, agent_id: str, menu_item_data: MenuItemCreate) -> MenuItem:
        """Create a new menu item for an agent"""
        try:
            # Verify agent exists
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
            if not agent:
                raise ValueError(f"Agent with ID {agent_id} not found")

            # Check if menu item number is unique for this agent (if provided)
            if menu_item_data.number:
                existing = db.query(MenuItem).filter(
                    MenuItem.agent_id == agent_id,
                    MenuItem.number == menu_item_data.number,
                    MenuItem.active == True
                ).first()
                if existing:
                    raise ValueError(f"Menu item number '{menu_item_data.number}' already exists for this agent")

            # Create new menu item
            menu_item = MenuItem(
                agent_id=agent_id,
                **menu_item_data.model_dump()
            )

            db.add(menu_item)
            db.commit()
            db.refresh(menu_item)

            app_logger.info(f"Created menu item {menu_item.id} for agent {agent_id}")
            return menu_item

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error creating menu item for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_menu_item(db: Session, agent_id: str, item_id: str) -> Optional[MenuItem]:
        """Get a specific menu item by ID"""
        return db.query(MenuItem).filter(
            MenuItem.id == item_id,
            MenuItem.agent_id == agent_id,
            MenuItem.active == True
        ).first()

    @staticmethod
    def get_menu_items(
        db: Session,
        agent_id: str,
        filters: Optional[MenuItemFilter] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Get paginated list of menu items with optional filtering"""
        try:
            # Build base query
            query = db.query(MenuItem).filter(
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            )

            # Apply filters
            if filters:
                if filters.category:
                    query = query.filter(MenuItem.category == filters.category)
                if filters.available is not None:
                    query = query.filter(MenuItem.available == filters.available)
                if filters.is_popular is not None:
                    query = query.filter(MenuItem.is_popular == filters.is_popular)
                if filters.is_special is not None:
                    query = query.filter(MenuItem.is_special == filters.is_special)
                if filters.is_new is not None:
                    query = query.filter(MenuItem.is_new == filters.is_new)
                if filters.is_limited_time is not None:
                    query = query.filter(MenuItem.is_limited_time == filters.is_limited_time)
                if filters.is_hidden is not None:
                    query = query.filter(MenuItem.is_hidden == filters.is_hidden)
                if filters.requires_age_check is not None:
                    query = query.filter(MenuItem.requires_age_check == filters.requires_age_check)
                if filters.has_discount is not None:
                    query = query.filter(MenuItem.has_discount == filters.has_discount)
                if filters.search:
                    search_term = f"%{filters.search}%"
                    query = query.filter(
                        or_(
                            MenuItem.name.ilike(search_term),
                            MenuItem.description.ilike(search_term),
                            MenuItem.ingredients.ilike(search_term)
                        )
                    )

            # Get total count
            total = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            items = query.order_by(MenuItem.category, MenuItem.name).offset(offset).limit(page_size).all()

            # Calculate pagination info
            total_pages = (total + page_size - 1) // page_size

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }

        except Exception as e:
            app_logger.error(f"Error getting menu items for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def update_menu_item(db: Session, agent_id: str, item_id: str, updates: MenuItemUpdate) -> MenuItem:
        """Update a menu item"""
        try:
            menu_item = db.query(MenuItem).filter(
                MenuItem.id == item_id,
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            ).first()

            if not menu_item:
                raise ValueError(f"Menu item {item_id} not found")

            # Check if menu item number is unique for this agent (if being updated)
            if updates.number and updates.number != menu_item.number:
                existing = db.query(MenuItem).filter(
                    MenuItem.agent_id == agent_id,
                    MenuItem.number == updates.number,
                    MenuItem.active == True,
                    MenuItem.id != item_id
                ).first()
                if existing:
                    raise ValueError(f"Menu item number '{updates.number}' already exists for this agent")

            # Apply updates
            update_data = updates.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(menu_item, field, value)

            menu_item.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(menu_item)

            app_logger.info(f"Updated menu item {item_id} for agent {agent_id}")
            return menu_item

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating menu item {item_id}: {str(e)}")
            raise

    @staticmethod
    def delete_menu_item(db: Session, agent_id: str, item_id: str) -> bool:
        """Soft delete a menu item"""
        try:
            menu_item = db.query(MenuItem).filter(
                MenuItem.id == item_id,
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            ).first()

            if not menu_item:
                raise ValueError(f"Menu item {item_id} not found")

            menu_item.active = False
            menu_item.updated_at = datetime.utcnow()
            db.commit()

            app_logger.info(f"Deleted menu item {item_id} for agent {agent_id}")
            return True

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error deleting menu item {item_id}: {str(e)}")
            raise

    @staticmethod
    def bulk_update_menu_items(db: Session, agent_id: str, item_ids: List[str], updates: MenuItemUpdate) -> List[MenuItem]:
        """Bulk update multiple menu items"""
        try:
            menu_items = db.query(MenuItem).filter(
                MenuItem.id.in_(item_ids),
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            ).all()

            if len(menu_items) != len(item_ids):
                found_ids = [item.id for item in menu_items]
                missing_ids = [item_id for item_id in item_ids if item_id not in found_ids]
                raise ValueError(f"Menu items not found: {missing_ids}")

            # Apply updates to all items
            update_data = updates.model_dump(exclude_unset=True)
            for menu_item in menu_items:
                for field, value in update_data.items():
                    setattr(menu_item, field, value)
                menu_item.updated_at = datetime.utcnow()

            db.commit()

            for menu_item in menu_items:
                db.refresh(menu_item)

            app_logger.info(f"Bulk updated {len(menu_items)} menu items for agent {agent_id}")
            return menu_items

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error bulk updating menu items for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_menu_categories(db: Session, agent_id: str) -> List[str]:
        """Get all unique categories for an agent's menu"""
        try:
            categories = db.query(MenuItem.category).filter(
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            ).distinct().all()

            return [str(cat[0]) for cat in categories if cat[0]]

        except Exception as e:
            app_logger.error(f"Error getting menu categories for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def toggle_availability(db: Session, agent_id: str, item_id: str) -> MenuItem:
        """Toggle the availability status of a menu item"""
        try:
            menu_item = db.query(MenuItem).filter(
                MenuItem.id == item_id,
                MenuItem.agent_id == agent_id,
                MenuItem.active == True
            ).first()

            if not menu_item:
                raise ValueError(f"Menu item {item_id} not found")

            menu_item.available = not menu_item.available
            menu_item.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(menu_item)

            app_logger.info(f"Toggled availability for menu item {item_id} to {menu_item.available}")
            return menu_item

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error toggling availability for menu item {item_id}: {str(e)}")
            raise
