from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timezone

from app.models import Agent, Order, OrderItem
from app.utils.logging_config import app_logger


class OrderService:
    """Service for managing orders directly linked to agents"""

    @staticmethod
    def create_order(db: Session, agent_id: str, order_data: Dict[str, Any]) -> Order:
        """Create a new order for an agent"""
        try:
            # Verify agent exists
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
            if not agent:
                raise ValueError(f"Agent with ID {agent_id} not found")

            # Extract order items data
            order_items_data = order_data.pop('order_items', [])
            if not order_items_data:
                raise ValueError("Cannot create an order with no items")

            # Calculate total price from items
            total_price = sum(item['quantity'] * item['price'] for item in order_items_data)

            # Create order
            new_order = Order(
                agent_id=agent_id,
                conversation_id=order_data['conversation_id'],
                customer_phone=order_data.get('customer_phone'),
                customer_name=order_data.get('customer_name'),
                status=order_data.get('status', 'new'),
                total_price=total_price
            )

            db.add(new_order)
            db.flush()  # Get the order ID

            # Create order items
            for item_data in order_items_data:
                order_item = OrderItem(
                    order_id=new_order.id,
                    name=item_data['name'],
                    quantity=item_data['quantity'],
                    price=item_data['price'],
                    note=item_data.get('note')
                )
                db.add(order_item)

            db.commit()
            db.refresh(new_order)

            app_logger.info(f"Created new order {new_order.id} for agent {agent_id}")
            return new_order

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error creating order for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_order_by_id(db: Session, order_id: str) -> Optional[Order]:
        """Get a specific order by ID with items loaded"""
        return (
            db.query(Order)
            .options(joinedload(Order.order_items))
            .filter(Order.id == order_id, Order.active == True)
            .first()
        )

    @staticmethod
    def get_agent_orders(
        db: Session,
        agent_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Order]:
        """Get all orders for a specific agent with optional date filtering"""
        try:
            # Verify agent exists
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
            if not agent:
                raise ValueError(f"Agent with ID {agent_id} not found")

            # Build query
            query = (
                db.query(Order)
                .options(joinedload(Order.order_items))
                .filter(Order.agent_id == agent_id, Order.active == True)
            )

            # Apply date filtering
            if start_date:
                start_datetime = datetime.combine(start_date, datetime.min.time())
                query = query.filter(Order.created_at >= start_datetime)

            if end_date:
                end_datetime = datetime.combine(end_date, datetime.max.time())
                query = query.filter(Order.created_at <= end_datetime)

            orders = query.order_by(Order.created_at.desc()).all()

            app_logger.info(f"Retrieved {len(orders)} orders for agent {agent_id}")
            return orders

        except Exception as e:
            app_logger.error(f"Error getting orders for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def update_order(db: Session, order_id: str, updates: Dict[str, Any]) -> Order:
        """Update an order's details"""
        try:
            order = (
                db.query(Order)
                .options(joinedload(Order.order_items))
                .filter(Order.id == order_id, Order.active == True)
                .first()
            )

            if not order:
                raise ValueError(f"Order {order_id} not found")

            # Update allowed fields
            allowed_fields = ['customer_name', 'customer_phone', 'status', 'total_price']
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(order, field, value)

            order.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(order)

            app_logger.info(f"Updated order {order_id}")
            return order

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating order {order_id}: {str(e)}")
            raise

    @staticmethod
    def update_order_item(db: Session, item_id: int, updates: Dict[str, Any]) -> OrderItem:
        """Update an order item's details"""
        try:
            order_item = db.query(OrderItem).filter(OrderItem.id == item_id).first()
            if not order_item:
                raise ValueError(f"Order item {item_id} not found")

            # Update allowed fields
            allowed_fields = ['name', 'quantity', 'price', 'note']
            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(order_item, field, value)

            # Update the parent order's updated_at timestamp
            order = db.query(Order).filter(Order.id == order_item.order_id).first()
            if order:
                order.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(order_item)

            app_logger.info(f"Updated order item {item_id}")
            return order_item

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating order item {item_id}: {str(e)}")
            raise

    @staticmethod
    def delete_order_item(db: Session, item_id: int) -> bool:
        """Delete an order item"""
        try:
            order_item = db.query(OrderItem).filter(OrderItem.id == item_id).first()
            if not order_item:
                raise ValueError(f"Order item {item_id} not found")

            order_id = order_item.order_id

            # Delete the item
            db.delete(order_item)

            # Update the parent order's updated_at timestamp
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.updated_at = datetime.now(timezone.utc)

            db.commit()

            app_logger.info(f"Deleted order item {item_id}")
            return True

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error deleting order item {item_id}: {str(e)}")
            raise

    @staticmethod
    def update_order_status(db: Session, order_id: str, new_status: str) -> Order:
        """Update an order's status"""
        try:
            order = db.query(Order).filter(Order.id == order_id, Order.active == True).first()
            if not order:
                raise ValueError(f"Order {order_id} not found")

            # Valid statuses
            valid_statuses = ['new', 'in_progress', 'ready', 'completed', 'cancelled']
            if new_status not in valid_statuses:
                raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

            order.status = new_status
            order.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(order)

            app_logger.info(f"Updated order {order_id} status to {new_status}")
            return order

        except Exception as e:
            db.rollback()
            app_logger.error(f"Error updating order {order_id} status: {str(e)}")
            raise
