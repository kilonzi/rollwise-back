"""
Order management tools for restaurant operations.
Provides comprehensive order and order item management capabilities.
"""
from typing import Dict, Any
from datetime import datetime

from app.models import get_db, Order, OrderItem, Conversation
from app.services.order_service import OrderService
from app.services.collection_service import CollectionService
from app.tools.registry import global_registry, tool
from app.utils.logging_config import app_logger


@tool(
    name="create_order",
    description="Start a new order for the current conversation",
    parameters={
        "type": "object",
        "properties": {
            "customer_name": {"type": "string", "description": "Customer's name"},
            "customer_phone": {"type": "string", "description": "Customer's phone number"},
            "order_items": {
                "type": "array",
                "description": "List of initial items for the order",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Item name"},
                        "quantity": {"type": "integer", "description": "Quantity"},
                        "price": {"type": "number", "description": "Price per item"},
                        "note": {"type": "string", "description": "Special instructions"}
                    },
                    "required": ["name", "quantity", "price"]
                }
            }
        },
        "required": ["order_items"]
    }
)
async def create_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new order for the current conversation"""
    try:
        conversation_id = args.get("conversation_id")
        if not conversation_id:
            return {"error": "Conversation ID is required"}

        db = next(get_db())
        try:
            # Get conversation to find agent_id
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()

            if not conversation:
                return {"error": "Conversation not found"}

            order_data = {
                "conversation_id": conversation_id,
                "customer_name": args.get("customer_name"),
                "customer_phone": args.get("customer_phone"),
                "order_items": args.get("order_items", [])
            }

            order = OrderService.create_order(db, conversation.agent_id, order_data)

            return {
                "success": True,
                "order_id": order.id,
                "total_price": order.total_price,
                "status": order.status,
                "message": f"Order {order.id} created successfully with {len(order.order_items)} items"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error creating order: {str(e)}")
        return {"error": f"Failed to create order: {str(e)}"}


@tool(
    name="get_order_by_conversation",
    description="Get the current order for this conversation",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
async def get_order_by_conversation(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get the current order for this conversation"""
    try:
        conversation_id = args.get("conversation_id")
        if not conversation_id:
            return {"error": "Conversation ID is required"}

        db = next(get_db())
        try:
            order = db.query(Order).filter(
                Order.conversation_id == conversation_id,
                Order.active == True
            ).first()

            if not order:
                return {"error": "No active order found for this conversation"}

            # Load order items
            items = []
            for item in order.order_items:
                items.append({
                    "id": item.id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "note": item.note,
                    "subtotal": item.quantity * item.price
                })

            return {
                "order_id": order.id,
                "status": order.status,
                "customer_name": order.customer_name,
                "customer_phone": order.customer_phone,
                "total_price": order.total_price,
                "items": items,
                "created_at": order.created_at.isoformat()
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error getting order: {str(e)}")
        return {"error": f"Failed to get order: {str(e)}"}


@tool(
    name="update_order",
    description="Update order status, customer info, or other details",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID to update"},
            "status": {"type": "string", "description": "New status (new, in_progress, ready, completed, cancelled)"},
            "customer_name": {"type": "string", "description": "Updated customer name"},
            "customer_phone": {"type": "string", "description": "Updated customer phone"},
            "total_price": {"type": "number", "description": "Updated total price"}
        },
        "required": ["order_id"]
    }
)
async def update_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update order details"""
    try:
        order_id = args.get("order_id")
        if not order_id:
            return {"error": "Order ID is required"}

        db = next(get_db())
        try:
            updates = {k: v for k, v in args.items() if k != "order_id" and k != "conversation_id"}
            order = OrderService.update_order(db, order_id, updates)

            return {
                "success": True,
                "order_id": order.id,
                "status": order.status,
                "message": "Order updated successfully"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error updating order: {str(e)}")
        return {"error": f"Failed to update order: {str(e)}"}


@tool(
    name="cancel_order",
    description="Cancel the entire order",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID to cancel"}
        },
        "required": ["order_id"]
    }
)
async def cancel_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel an order"""
    try:
        order_id = args.get("order_id")
        if not order_id:
            return {"error": "Order ID is required"}

        db = next(get_db())
        try:
            order = OrderService.update_order_status(db, order_id, "cancelled")
            return {
                "success": True,
                "order_id": order.id,
                "status": order.status,
                "message": "Order cancelled successfully"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error cancelling order: {str(e)}")
        return {"error": f"Failed to cancel order: {str(e)}"}


@tool(
    name="get_order_status",
    description="Check the current status of an order",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID to check"}
        },
        "required": ["order_id"]
    }
)
async def get_order_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get order status"""
    try:
        order_id = args.get("order_id")
        if not order_id:
            return {"error": "Order ID is required"}

        db = next(get_db())
        try:
            order = OrderService.get_order_by_id(db, order_id)
            if not order:
                return {"error": "Order not found"}

            return {
                "order_id": order.id,
                "status": order.status,
                "total_price": order.total_price,
                "item_count": len(order.order_items),
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat()
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error getting order status: {str(e)}")
        return {"error": f"Failed to get order status: {str(e)}"}


@tool(
    name="complete_order",
    description="Mark an order as completed",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID to complete"}
        },
        "required": ["order_id"]
    }
)
async def complete_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Mark order as completed"""
    try:
        order_id = args.get("order_id")
        if not order_id:
            return {"error": "Order ID is required"}

        db = next(get_db())
        try:
            order = OrderService.update_order_status(db, order_id, "completed")
            return {
                "success": True,
                "order_id": order.id,
                "status": order.status,
                "message": "Order marked as completed"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error completing order: {str(e)}")
        return {"error": f"Failed to complete order: {str(e)}"}


@tool(
    name="list_orders_for_customer",
    description="Get all orders for a customer by phone number",
    parameters={
        "type": "object",
        "properties": {
            "customer_phone": {"type": "string", "description": "Customer's phone number"},
            "limit": {"type": "integer", "description": "Maximum number of orders to return (default: 10)"}
        },
        "required": ["customer_phone"]
    }
)
async def list_orders_for_customer(args: Dict[str, Any]) -> Dict[str, Any]:
    """List all orders for a customer"""
    try:
        customer_phone = args.get("customer_phone")
        limit = args.get("limit", 10)

        if not customer_phone:
            return {"error": "Customer phone is required"}

        conversation_id = args.get("conversation_id")
        if not conversation_id:
            return {"error": "Conversation ID is required"}

        db = next(get_db())
        try:
            # Get conversation to find agent_id
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()

            if not conversation:
                return {"error": "Conversation not found"}

            orders = db.query(Order).filter(
                Order.agent_id == conversation.agent_id,
                Order.customer_phone == customer_phone,
                Order.active == True
            ).order_by(Order.created_at.desc()).limit(limit).all()

            order_list = []
            for order in orders:
                order_list.append({
                    "order_id": order.id,
                    "status": order.status,
                    "total_price": order.total_price,
                    "item_count": len(order.order_items),
                    "created_at": order.created_at.isoformat()
                })

            return {
                "customer_phone": customer_phone,
                "order_count": len(order_list),
                "orders": order_list
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error listing customer orders: {str(e)}")
        return {"error": f"Failed to list customer orders: {str(e)}"}


@tool(
    name="add_order_item",
    description="Add an item to an existing order",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID to add item to"},
            "name": {"type": "string", "description": "Item name"},
            "quantity": {"type": "integer", "description": "Quantity"},
            "price": {"type": "number", "description": "Price per item"},
            "note": {"type": "string", "description": "Special instructions"}
        },
        "required": ["order_id", "name", "quantity", "price"]
    }
)
async def add_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add an item to an order"""
    try:
        order_id = args.get("order_id")
        if not order_id:
            return {"error": "Order ID is required"}

        db = next(get_db())
        try:
            # Verify order exists
            order = db.query(Order).filter(Order.id == order_id, Order.active == True).first()
            if not order:
                return {"error": "Order not found"}

            # Create new order item
            new_item = OrderItem(
                order_id=order_id,
                name=args.get("name"),
                quantity=args.get("quantity"),
                price=args.get("price"),
                note=args.get("note")
            )

            db.add(new_item)

            # Update order total
            total_price = sum(
                item.quantity * item.price
                for item in order.order_items
            ) + (new_item.quantity * new_item.price)

            order.total_price = total_price
            order.updated_at = datetime.now()

            db.commit()
            db.refresh(new_item)

            return {
                "success": True,
                "item_id": new_item.id,
                "order_id": order_id,
                "subtotal": new_item.quantity * new_item.price,
                "new_total": total_price,
                "message": f"Added {args.get('name')} to order"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error adding order item: {str(e)}")
        return {"error": f"Failed to add order item: {str(e)}"}


@tool(
    name="change_order_item",
    description="Update an existing order item (quantity, price, or notes)",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "Order item ID to update"},
            "name": {"type": "string", "description": "Updated item name"},
            "quantity": {"type": "integer", "description": "Updated quantity"},
            "price": {"type": "number", "description": "Updated price per item"},
            "note": {"type": "string", "description": "Updated special instructions"}
        },
        "required": ["item_id"]
    }
)
async def change_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update an order item"""
    try:
        item_id = args.get("item_id")
        if not item_id:
            return {"error": "Item ID is required"}

        db = next(get_db())
        try:
            updates = {k: v for k, v in args.items() if k != "item_id" and k != "conversation_id"}
            item = OrderService.update_order_item(db, item_id, updates)

            # Recalculate order total
            order = db.query(Order).filter(Order.id == item.order_id).first()
            if order:
                total_price = sum(oi.quantity * oi.price for oi in order.order_items)
                order.total_price = total_price
                db.commit()

            return {
                "success": True,
                "item_id": item.id,
                "order_id": item.order_id,
                "subtotal": item.quantity * item.price,
                "message": "Order item updated successfully"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error updating order item: {str(e)}")
        return {"error": f"Failed to update order item: {str(e)}"}


@tool(
    name="remove_order_item",
    description="Remove an item from an order",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "Order item ID to remove"}
        },
        "required": ["item_id"]
    }
)
async def remove_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove an item from an order"""
    try:
        item_id = args.get("item_id")
        if not item_id:
            return {"error": "Item ID is required"}

        db = next(get_db())
        try:
            # Get item before deleting to calculate new total
            item = db.query(OrderItem).filter(OrderItem.id == item_id).first()
            if not item:
                return {"error": "Order item not found"}

            order_id = item.order_id
            item_name = item.name

            success = OrderService.delete_order_item(db, item_id)

            if success:
                # Recalculate order total
                order = db.query(Order).filter(Order.id == order_id).first()
                if order:
                    total_price = sum(oi.quantity * oi.price for oi in order.order_items)
                    order.total_price = total_price
                    db.commit()

                return {
                    "success": True,
                    "order_id": order_id,
                    "message": f"Removed {item_name} from order"
                }
            else:
                return {"error": "Failed to remove item"}
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error removing order item: {str(e)}")
        return {"error": f"Failed to remove order item: {str(e)}"}


@tool(
    name="list_menu",
    description="Show available menu items from restaurant collections",
    parameters={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Filter by category (optional)"},
            "search_term": {"type": "string", "description": "Search for specific items (optional)"}
        },
        "required": []
    }
)
async def list_menu(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get menu items from collections"""
    try:
        conversation_id = args.get("conversation_id")
        if not conversation_id:
            return {"error": "Conversation ID is required"}

        db = next(get_db())
        try:
            # Get conversation to find agent_id
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()

            if not conversation:
                return {"error": "Conversation not found"}

            # Search for menu collections
            search_term = args.get("search_term", "menu")
            category = args.get("category")

            if category:
                search_term = f"{search_term} {category}"

            collection_service = CollectionService(db)
            results = collection_service.search_collection(
                conversation.agent_id, "menu", search_term, limit=20
            )

            if not results.get("results"):
                return {
                    "message": "No menu items found",
                    "items": []
                }

            # Format results as menu items
            menu_items = []
            for result in results["results"]:
                menu_items.append({
                    "content": result.get("content", ""),
                    "relevance_score": result.get("distance", 0),
                    "source": result.get("metadata", {}).get("filename", "menu")
                })

            return {
                "menu_items": menu_items,
                "total_found": len(menu_items),
                "search_term": search_term
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error getting menu: {str(e)}")
        return {"error": f"Failed to get menu: {str(e)}"}


@tool(
    name="customize_order_item",
    description="Add or update special instructions/notes for an order item",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "Order item ID to customize"},
            "note": {"type": "string", "description": "Special instructions (e.g., 'extra spicy', 'no onions', 'sauce on the side')"}
        },
        "required": ["item_id", "note"]
    }
)
async def customize_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add special instructions to an order item"""
    try:
        item_id = args.get("item_id")
        note = args.get("note")

        if not item_id or not note:
            return {"error": "Item ID and note are required"}

        db = next(get_db())
        try:
            item = OrderService.update_order_item(db, item_id, {"note": note})

            return {
                "success": True,
                "item_id": item.id,
                "item_name": item.name,
                "note": item.note,
                "message": f"Added customization: {note}"
            }
        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error customizing order item: {str(e)}")
        return {"error": f"Failed to customize order item: {str(e)}"}


# Register all tools with the global registry
def register_order_tools():
    """Register all order tools with the global registry"""
    tools_to_register = [
        update_order,
        cancel_order,
        get_order_status,
        complete_order,
        list_orders_for_customer,
        add_order_item,
        change_order_item,
        remove_order_item,
        list_menu,
        customize_order_item
    ]

    for tool_func in tools_to_register:
        global_registry.register(
            name=tool_func._tool_name,
            description=tool_func._tool_description,
            parameters=tool_func._tool_parameters
        )(tool_func)

    app_logger.info(f"Registered {len(tools_to_register)} order tools")


# Auto-register when module is imported
register_order_tools()
