"""
Order management tools for restaurant operations.
Provides comprehensive order management functionality including adding/removing items,
updating orders, getting summaries, finalizing orders, and checking order status.
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import get_db, Order, OrderItem, MenuItem
from app.tools.registry import tool, global_registry
from app.utils.logging_config import app_logger


@tool(
    name="add_order_item",
    description="""Add an item to the current order.
    Use this function when customers want to order food/products.
    
    Always confirm the item exists on the menu before adding.
    Ask for quantity if not specified by the customer.
    
    Examples:
    - "I'd like a burger" → add_order_item(order_id="123", item_id="burger_001", quantity=1)
    - "Can I get 2 pizzas with extra cheese?" → add_order_item(order_id="123", item_id="pizza_001", quantity=2, notes="extra cheese")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID to add items to",
            },
            "item_id": {
                "type": "string",
                "description": "The menu item ID from the menu_items table",
            },
            "quantity": {
                "type": "integer",
                "description": "Quantity of the item",
                "default": 1,
                "minimum": 1,
            },
            "notes": {
                "type": "string",
                "description": "Any special instructions, modifications, or notes for the item",
            },
        },
        "required": ["order_id", "item_id"],
    },
)
async def add_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add an item to an existing order by looking up menu item details"""
    try:
        order_id = args.get("order_id")
        item_id = args.get("item_id")
        quantity = args.get("quantity", 1)
        notes = args.get("notes")

        if not all([order_id, item_id]):
            return {"error": "order_id and item_id are required"}

        if quantity < 1:
            return {"error": "Quantity must be at least 1"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Find the menu item
            menu_item = (
                db.query(MenuItem)
                .filter(
                    MenuItem.id == item_id,
                    MenuItem.active == True,
                    MenuItem.available == True,
                )
                .first()
            )

            if not menu_item:
                return {
                    "error": f"Menu item with ID {item_id} not found or unavailable"
                }

            # Create the order item
            order_item = OrderItem(
                order_id=order_id,
                name=menu_item.name,
                quantity=quantity,
                price=menu_item.price,
                note=notes,
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
                "pickup_time": order.pickup_time,
                "special_requests": order.special_requests,
                "confirmed_at": order.confirmed_at.isoformat()
                if order.confirmed_at
                else None,
                "notes": notes,
                "message": f"Added {quantity}x {menu_item.name} to order {order_id}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error adding order item: {str(e)}")
        return {"error": f"Failed to add order item: {str(e)}"}


@tool(
    name="remove_order_item",
    description="""Remove an item from the current order.
    Use this function when customers want to remove items they previously ordered.
    
    Examples:
    - "Remove the burger from my order" → remove_order_item(order_id="123", item_name="burger")
    - "Take off one pizza" → remove_order_item(order_id="123", item_name="pizza", quantity=1)
    - "Remove all the fries" → remove_order_item(order_id="123", item_name="fries")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID to remove items from",
            },
            "item_name": {
                "type": "string",
                "description": "Name of the menu item to remove (matches what's in the order)",
            },
            "quantity": {
                "type": "integer",
                "description": "Quantity to remove (if not specified, removes all of this item)",
                "minimum": 1,
            },
        },
        "required": ["order_id", "item_name"],
    },
)
async def remove_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove items from an existing order"""
    try:
        order_id = args.get("order_id")
        item_name = args.get("item_name")
        quantity_to_remove = args.get("quantity")

        if not all([order_id, item_name]):
            return {"error": "order_id and item_name are required"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Find the order item(s)
            order_items = (
                db.query(OrderItem)
                .filter(
                    and_(
                        OrderItem.order_id == order_id,
                        OrderItem.name.ilike(f"%{item_name}%"),
                    )
                )
                .all()
            )

            if not order_items:
                return {"error": f"Item '{item_name}' not found in order {order_id}"}

            total_removed = 0
            total_refund = 0
            removed_items = []

            for order_item in order_items:
                if quantity_to_remove is None:
                    # Remove all of this item
                    removed_qty = order_item.quantity
                    refund_amount = order_item.price * order_item.quantity
                    db.delete(order_item)
                    removed_items.append(f"{removed_qty}x {order_item.name}")
                else:
                    # Remove specific quantity
                    if order_item.quantity <= quantity_to_remove:
                        # Remove entire item
                        removed_qty = order_item.quantity
                        refund_amount = order_item.price * order_item.quantity
                        db.delete(order_item)
                        removed_items.append(f"{removed_qty}x {order_item.name}")
                        quantity_to_remove -= removed_qty
                    else:
                        # Reduce quantity
                        removed_qty = quantity_to_remove
                        refund_amount = order_item.price * quantity_to_remove
                        order_item.quantity -= quantity_to_remove
                        removed_items.append(f"{removed_qty}x {order_item.name}")
                        quantity_to_remove = 0

                total_removed += removed_qty
                total_refund += refund_amount

                if quantity_to_remove == 0:
                    break

            # Update order total
            order.total_price = max(0, (order.total_price or 0) - total_refund)

            db.commit()

            return {
                "success": True,
                "order_id": order_id,
                "removed_items": removed_items,
                "total_removed": total_removed,
                "refund_amount": total_refund,
                "new_order_total": order.total_price,
                "pickup_time": order.pickup_time,
                "special_requests": order.special_requests,
                "confirmed_at": order.confirmed_at.isoformat()
                if order.confirmed_at
                else None,
                "message": f"Removed {', '.join(removed_items)} from order {order_id}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error removing order item: {str(e)}")
        return {"error": f"Failed to remove order item: {str(e)}"}


@tool(
    name="update_order_item",
    description="""Update an existing item in the current order.
    Use this function when customers want to modify quantity or special instructions.
    
    Examples:
    - "Change my burger quantity to 2" → update_order_item(order_id="123", item_name="burger", new_quantity=2)
    - "Make my pizza with no cheese" → update_order_item(order_id="123", item_name="pizza", new_notes="no cheese")
    - "I want 3 burgers with extra pickles" → update_order_item(order_id="123", item_name="burger", new_quantity=3, new_notes="extra pickles")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID containing the item to update",
            },
            "item_name": {
                "type": "string",
                "description": "Name of the menu item to update",
            },
            "new_quantity": {
                "type": "integer",
                "description": "New quantity for the item",
                "minimum": 1,
            },
            "new_notes": {
                "type": "string",
                "description": "Updated special instructions for the item",
            },
        },
        "required": ["order_id", "item_name"],
    },
)
async def update_order_item(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing item in an order"""
    try:
        order_id = args.get("order_id")
        item_name = args.get("item_name")
        new_quantity = args.get("new_quantity")
        new_notes = args.get("new_notes")

        if not all([order_id, item_name]):
            return {"error": "order_id and item_name are required"}

        if new_quantity is not None and new_quantity < 1:
            return {"error": "New quantity must be at least 1"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Find the order item
            order_item = (
                db.query(OrderItem)
                .filter(
                    and_(
                        OrderItem.order_id == order_id,
                        OrderItem.name.ilike(f"%{item_name}%"),
                    )
                )
                .first()
            )

            if not order_item:
                return {"error": f"Item '{item_name}' not found in order {order_id}"}

            old_total = order_item.price * order_item.quantity
            changes = []

            # Update quantity if provided
            if new_quantity is not None:
                old_qty = order_item.quantity
                order_item.quantity = new_quantity
                changes.append(f"quantity: {old_qty} → {new_quantity}")

            # Update notes if provided
            if new_notes is not None:
                old_notes = order_item.note or "none"
                order_item.note = new_notes
                changes.append(f"notes: '{old_notes}' → '{new_notes}'")

            # Recalculate order total
            new_item_total = order_item.price * order_item.quantity
            total_difference = new_item_total - old_total
            order.total_price = (order.total_price or 0) + total_difference

            db.commit()

            return {
                "success": True,
                "order_id": order_id,
                "item_name": order_item.name,
                "changes": changes,
                "new_quantity": order_item.quantity,
                "new_notes": order_item.note,
                "new_item_total": new_item_total,
                "new_order_total": order.total_price,
                "pickup_time": order.pickup_time,
                "special_requests": order.special_requests,
                "confirmed_at": order.confirmed_at.isoformat()
                if order.confirmed_at
                else None,
                "message": f"Updated {order_item.name}: {', '.join(changes)}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error updating order item: {str(e)}")
        return {"error": f"Failed to update order item: {str(e)}"}


@tool(
    name="get_order_summary",
    description="""Get a summary of the current order including all items and total price.
    Use this function when customers ask "What's in my order?" or want to review their order.
    
    Examples:
    - "What do I have in my order?" → get_order_summary(order_id="123")
    - "Can you read back my order?" → get_order_summary(order_id="123")
    - "What's my total?" → get_order_summary(order_id="123")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID to get summary for",
            }
        },
        "required": ["order_id"],
    },
)
async def get_order_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get a complete summary of an order"""
    try:
        order_id = args.get("order_id")

        if not order_id:
            return {"error": "order_id is required"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Get all order items
            order_items = (
                db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
            )

            items_summary = []
            for item in order_items:
                item_data = {
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": item.price,
                    "total_price": item.price * item.quantity,
                    "notes": item.note or "",
                }
                items_summary.append(item_data)

            return {
                "success": True,
                "order_id": order_id,
                "customer_phone": order.customer_phone,
                "customer_name": order.customer_name,
                "status": order.status,
                "active": order.active,
                "items": items_summary,
                "total_items": len(items_summary),
                "total_price": order.total_price or 0,
                "pickup_time": order.pickup_time,
                "special_requests": order.special_requests,
                "confirmed_at": order.confirmed_at.isoformat()
                if order.confirmed_at
                else None,
                "created_at": order.created_at.isoformat()
                if order.created_at
                else None,
                "message": f"Order {order_id} contains {len(items_summary)} items totaling ${order.total_price or 0:.2f}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error getting order summary: {str(e)}")
        return {"error": f"Failed to get order summary: {str(e)}"}


@tool(
    name="finalize_order",
    description="""Finalize the current order for processing and set it to active status.
    Use this function when customers are ready to place their order and have confirmed all items.
    This will activate the order, calculate final totals, and prepare it for kitchen/fulfillment.
    
    Examples:
    - "I'm ready to place my order" → finalize_order(order_id="123")
    - "That's everything, place the order" → finalize_order(order_id="123", customer_name="John Smith")
    - "Complete my order for pickup in 45 minutes" → finalize_order(order_id="123", customer_name="Jane", pickup_time="45 minutes")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order ID to finalize"},
            "customer_name": {
                "type": "string",
                "description": "Customer's name for the order",
            },
            "pickup_time": {
                "type": "string",
                "description": "Requested pickup time (e.g., 'ASAP', '2:30 PM', '45 minutes'). Defaults to 30 minutes from now.",
            },
            "special_requests": {
                "type": "string",
                "description": "Any special requests for the entire order",
            },
        },
        "required": ["order_id", "customer_name"],
    },
)
async def finalize_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Finalize an order by setting it to active and updating details"""
    try:
        order_id = args.get("order_id")
        customer_name = args.get("customer_name", "Guest")
        pickup_time = args.get("pickup_time")
        special_requests = args.get("special_requests", "none")

        if not order_id:
            return {"error": "order_id is required"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Check if order has items
            order_items = (
                db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
            )
            if not order_items:
                return {"error": "Cannot finalize empty order. Please add items first."}

            # Set confirmation time to now
            confirmed_at = datetime.utcnow()

            # Set default pickup time to 30 minutes from now if not provided
            if not pickup_time:
                pickup_time = (confirmed_at + timedelta(minutes=30)).strftime(
                    "%I:%M %p"
                )

            # Update order details
            order.active = True
            order.customer_name = customer_name
            order.pickup_time = pickup_time
            order.special_requests = special_requests
            order.confirmed_at = confirmed_at
            order.updated_at = confirmed_at

            # Recalculate final total
            final_total = sum(item.price * item.quantity for item in order_items)
            order.total_price = final_total

            db.commit()

            return {
                "success": True,
                "order_id": order_id,
                "status": "confirmed",
                "active": True,
                "customer_name": order.customer_name,
                "customer_phone": order.customer_phone,
                "pickup_time": order.pickup_time,
                "special_requests": order.special_requests,
                "total_items": len(order_items),
                "final_total": final_total,
                "confirmed_at": order.confirmed_at.isoformat(),
                "message": f"Order {order_id} has been confirmed and activated. Total: ${final_total:.2f}. Pickup: {pickup_time}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error finalizing order: {str(e)}")
        return {"error": f"Failed to finalize order: {str(e)}"}


@tool(
    name="find_customer_orders",
    description="""Find and check status of customer orders by phone number.
    Use this function when someone calls to check on their existing orders.
    
    Examples:
    - "I want to check my order status" → find_customer_orders(phone_number="+1234567890")
    - "Has my order been confirmed?" → find_customer_orders(phone_number="+1234567890", status="confirmed")
    - "What orders do I have today?" → find_customer_orders(phone_number="+1234567890", active_only=True)
    """,
    parameters={
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "Customer's phone number to search for orders",
            },
            "status": {
                "type": "string",
                "description": "Filter by order status (e.g., 'pending', 'confirmed', 'completed')",
            },
            "active_only": {
                "type": "boolean",
                "description": "Only return active orders",
                "default": True,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of orders to return",
                "default": 2,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["phone_number"],
    },
)
async def find_customer_orders(args: Dict[str, Any]) -> Dict[str, Any]:
    """Find customer orders by phone number and check their status"""
    try:
        phone_number = args.get("phone_number")
        status_filter = args.get("status")
        active_only = args.get("active_only", True)
        limit = args.get("limit", 5)

        if not phone_number:
            return {"error": "phone_number is required"}

        db: Session = next(get_db())
        try:
            # Build query
            query = db.query(Order).filter(Order.customer_phone == phone_number)

            if active_only:
                query = query.filter(Order.active == True)

            if status_filter:
                query = query.filter(Order.status == status_filter)

            # Get orders sorted by creation date (newest first)
            orders = query.order_by(Order.created_at.desc()).limit(limit).all()

            if not orders:
                filter_desc = " (active only)" if active_only else ""
                filter_desc += f" (status: {status_filter})" if status_filter else ""
                return {
                    "success": True,
                    "orders": [],
                    "total_found": 0,
                    "message": f"No orders found for {phone_number}{filter_desc}",
                }

            orders_summary = []
            for order in orders:
                # Get order items
                order_items = (
                    db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
                )

                order_data = {
                    "order_id": order.id,
                    "status": order.status,
                    "active": order.active,
                    "total_price": order.total_price or 0,
                    "total_items": len(order_items),
                    "customer_name": order.customer_name,
                    "pickup_time": order.pickup_time,
                    "special_requests": order.special_requests,
                    "created_at": order.created_at.isoformat()
                    if order.created_at
                    else None,
                    "confirmed_at": order.confirmed_at.isoformat()
                    if order.confirmed_at
                    else None,
                    "items": [
                        {
                            "name": item.name,
                            "quantity": item.quantity,
                            "price": item.price,
                            "notes": item.note or "",
                        }
                        for item in order_items
                    ],
                }
                orders_summary.append(order_data)

            return {
                "success": True,
                "phone_number": phone_number,
                "orders": orders_summary,
                "total_found": len(orders),
                "message": f"Found {len(orders)} order(s) for {phone_number}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error finding customer orders: {str(e)}")
        return {"error": f"Failed to find customer orders: {str(e)}"}


@tool(
    name="cancel_order",
    description="""Cancel an existing order if it's eligible for cancellation.
    Use this function when customers want to cancel their order.
    
    Orders can only be cancelled if they are:
    - Active (active=True)
    - Not in progress (status != 'in_progress')
    
    Examples:
    - "I want to cancel my order" → cancel_order(order_id="123")
    - "Can you cancel order 456?" → cancel_order(order_id="456")
    - "I need to cancel my recent order" → cancel_order(order_id="789", reason="customer_request")
    """,
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order ID to cancel"},
            "reason": {
                "type": "string",
                "description": "Reason for cancellation (optional)",
                "enum": [
                    "customer_request",
                    "item_unavailable",
                    "payment_issue",
                    "duplicate_order",
                    "other",
                ],
                "default": "customer_request",
            },
        },
        "required": ["order_id"],
    },
)
async def cancel_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel an order if it meets cancellation criteria"""
    try:
        order_id = args.get("order_id")
        reason = args.get("reason", "customer_request")

        if not order_id:
            return {"error": "order_id is required"}

        db: Session = next(get_db())
        try:
            # Find the order
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"error": f"Order with ID {order_id} not found"}

            # Check if order is eligible for cancellation
            if not order.active:
                return {
                    "error": f"Order {order_id} is already inactive and cannot be cancelled"
                }

            if order.status == "in_progress":
                return {
                    "error": f"Order {order_id} is currently in progress and cannot be cancelled. Please contact the restaurant directly."
                }

            if order.status == "completed":
                return {
                    "error": f"Order {order_id} is already completed and cannot be cancelled"
                }

            if order.status == "cancelled":
                return {"error": f"Order {order_id} is already cancelled"}

            # Get order items for refund calculation
            order_items = (
                db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
            )
            refund_amount = order.total_price or 0

            # Cancel the order
            order.active = False
            order.status = "cancelled"
            order.cancellation_reason = reason
            order.cancelled_at = datetime.utcnow()
            order.updated_at = datetime.utcnow()

            db.commit()

            return {
                "success": True,
                "order_id": order_id,
                "status": "cancelled",
                "active": False,
                "customer_name": order.customer_name,
                "customer_phone": order.customer_phone,
                "cancellation_reason": reason,
                "cancelled_at": order.cancelled_at.isoformat(),
                "refund_amount": refund_amount,
                "total_items_cancelled": len(order_items),
                "message": f"Order {order_id} has been successfully cancelled. Refund amount: ${refund_amount:.2f}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error cancelling order: {str(e)}")
        return {"error": f"Failed to cancel order: {str(e)}"}


@tool(
    name="hangup_function",
    description="""Signal to end the conversation and close the connection.

    Use this function when:
    - The conversation has naturally concluded
    - User hasn't responded after asking "Are you there?" or similar
    - User explicitly says goodbye or indicates they want to end the call
    - You've provided all requested information and no further assistance is needed

    Always be polite before hanging up. Say something like "Thank you for calling! Have a great day!"
    """,
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Brief reason for hanging up",
                "enum": [
                    "conversation_complete",
                    "user_inactive",
                    "user_goodbye",
                    "no_response",
                ],
                "default": "conversation_complete",
            }
        },
        "required": [],
    },
)
async def hangup_function(args: Dict[str, Any]) -> Dict[str, Any]:
    """End the conversation gracefully"""
    try:
        reason = args.get("reason", "conversation_complete")

        app_logger.info(f"[HANGUP] Function called with reason: {reason}")

        # Return result that triggers both hangup mechanisms
        result = {
            "success": True,
            "action": "hangup",  # Triggers first hangup mechanism (line 272)
            "reason": reason,
            "message": "Thank you for calling! Have a great day!",
            "_trigger_close": True,  # Triggers second hangup mechanism (line 328)
        }

        app_logger.info(
            f"[HANGUP] Returning result to trigger call termination: {result}"
        )
        return result

    except Exception as e:
        app_logger.error(f"[HANGUP] Error in hangup function: {str(e)}")
        return {
            "error": f"Failed to end conversation: {str(e)}",
            "action": "hangup",
            "_trigger_close": True,  # Still try to close even on error
        }


# Register all tools
tools_to_register = [
    add_order_item,
    remove_order_item,
    update_order_item,
    get_order_summary,
    finalize_order,
    find_customer_orders,
    cancel_order,
    hangup_function,
]

for tool_func in tools_to_register:
    try:
        global_registry.register(
            name=tool_func._tool_name,
            description=tool_func._tool_description,
            parameters=tool_func._tool_parameters,
        )(tool_func)
        app_logger.info(f"Successfully registered {tool_func._tool_name} tool")
    except Exception as e:
        app_logger.error(f"Failed to register {tool_func._tool_name} tool: {e}")
