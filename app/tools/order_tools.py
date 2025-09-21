"""
Order management tools for restaurant operations.
Provides a single tool for adding items to orders.
"""
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.models import get_db, Order, OrderItem, MenuItem
from app.tools.registry import tool, global_registry
from app.utils.logging_config import app_logger


@tool(
    name="add_order_item",
    description="Attach an existing menu item to an existing order. The order and menu item already exist at this point, so this action only needs to link them together with a quantity.",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The unique ID of the order that the item should be added to."
            },
            "menu_item_id": {
                "type": "string",
                "description": "The unique ID of the menu item being added. This must match an existing menu item."
            },
            "quantity": {
                "type": "integer",
                "description": "How many units of this menu item to add to the order.",
                "minimum": 1
            }
        },
        "required": ["order_id", "menu_item_id", "quantity"]
    }
)
async def add_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add an item to an existing order by looking up menu item details"""
    try:
        order_id = args.get("order_id")
        menu_item_id = args.get("menu_item_id")
        quantity = args.get("quantity")

        if not all([order_id, menu_item_id, quantity]):
            return {"error": "order_id, menu_item_id, and quantity are required"}

        if quantity < 1:
            return {"error": "Quantity must be at least 1"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Find the menu item
            menu_item = db.query(MenuItem).filter(
                MenuItem.id == menu_item_id,
                MenuItem.active == True,
                MenuItem.available == True
            ).first()

            if not menu_item:
                return {"error": f"Menu item with ID {menu_item_id} not found or unavailable"}

            # Create the order item
            order_item = OrderItem(
                order_id=order_id,
                name=menu_item.name,
                quantity=quantity,
                price=menu_item.price
            )

            db.add(order_item)

            # Update order total
            item_total = menu_item.price * quantity
            order.total_price = (order.total_price or 0) + item_total

            db.commit()
            db.refresh(order_item)

            return {
                "success": True,
                "order_item_id": order_item.id,
                "order_id": order_id,
                "item_name": menu_item.name,
                "quantity": quantity,
                "unit_price": menu_item.price,
                "item_total": item_total,
                "order_total": order.total_price,
                "message": f"Added {quantity}x {menu_item.name} to order {order_id}"
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error adding order item: {str(e)}")
        return {"error": f"Failed to add order item: {str(e)}"}


# Register the tool directly when module is imported
try:
    global_registry.register(
        name=add_order_item._tool_name,
        description=add_order_item._tool_description,
        parameters=add_order_item._tool_parameters
    )(add_order_item)
    app_logger.info("Successfully registered add_order_item tool")
except Exception as e:
    app_logger.error(f"Failed to register add_order_item tool: {e}")
