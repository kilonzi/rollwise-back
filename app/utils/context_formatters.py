"""
Context formatting utilities for agent configuration
"""

from datetime import datetime


def format_business_context(agent) -> str:
    """Format business details into context string"""
    context_parts = []

    # Business name and type
    business_name = getattr(agent, 'business_name', None) or agent.name or "the business"
    context_parts.append(f"Business: {business_name}")

    # Business hours
    if agent.business_hours:
        days_map = {
            1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
            5: "Friday", 6: "Saturday", 7: "Sunday"
        }
        business_days = [
            days_map.get(day, str(day))
            for day in agent.business_hours.get("days", [1, 2, 3, 4, 5])
        ]
        start_time = agent.business_hours.get("start", "09:00")
        end_time = agent.business_hours.get("end", "17:00")
        timezone = agent.business_hours.get("timezone", "UTC")

        context_parts.append(
            f"Hours: {', '.join(business_days)} {start_time}-{end_time} ({timezone})"
        )

    # Booking settings
    if agent.booking_enabled:
        booking_details = []
        if agent.default_slot_duration:
            booking_details.append(f"{agent.default_slot_duration}min appointments")
        if agent.buffer_time:
            booking_details.append(f"{agent.buffer_time}min buffer")
        if agent.max_slot_appointments:
            if agent.max_slot_appointments == 1:
                booking_details.append("no overlapping appointments")
            else:
                booking_details.append(f"max {agent.max_slot_appointments} per slot")

        if booking_details:
            context_parts.append(f"Booking: {', '.join(booking_details)}")
    else:
        context_parts.append("Booking: disabled")

    # Blocked dates
    if agent.blocked_dates:
        context_parts.append(f"Unavailable: {', '.join(agent.blocked_dates)}")

    return " | ".join(context_parts)


def format_conversation_item(conv, index: int) -> str:
    """Format a single conversation for history display"""
    days_ago = (datetime.now() - conv.created_at).days
    time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

    text = f"{index}. {time_desc}: {conv.summary}\n"
    if conv.conversation_type:
        text += f"   Type: {conv.conversation_type}\n"
    return text


def format_order_item(order, index: int) -> str:
    """Format a single order for history display"""
    days_ago = (datetime.now() - order.created_at).days
    time_desc = "today" if days_ago == 0 else f"{days_ago} days ago"

    text = f"{index}. {time_desc} - ${order.total_price:.2f} ({order.status})\n"

    # Add order items
    if order.order_items:
        for item in order.order_items[:3]:  # Show max 3 items
            text += f"   • {item.quantity}x {item.name} @ ${item.price:.2f}\n"

        if len(order.order_items) > 3:
            text += f"   ... and {len(order.order_items) - 3} more items\n"

    return text


def format_current_order_context(order) -> str:
    """Format current order context"""
    context_parts = [
        "CURRENT ORDER (ALWAYS USE THIS ORDER):",
        f"- Order ID: {order.id}",
        f"- Customer Phone Number: {order.customer_phone}",
    ]

    # Add current order items
    if order.order_items:
        context_parts.append("- Current Items:")
        for item in order.order_items:
            context_parts.append(f"  • {item.quantity}x {item.name}")
            if item.note:
                context_parts.append(f"    Note: {item.note}")
    else:
        context_parts.append("- Current Items: None (empty order)")

    context_parts.extend([
        "",
        "IMPORTANT ORDER INSTRUCTIONS:",
        f"- ALWAYS use Order ID {order.id} for all order operations",
        "- NEVER create a new order during this conversation",
        "- Add/modify/remove items using the existing order tools",
        "- This order already exists and is ready for items",
        "- You must always call finalize_order, this is the only way it's useful",
        "- You must always get the customer's name for the order",
    ])

    return "\n".join(context_parts)


def format_menu_item(item) -> str:
    """Format a single menu item"""
    text = f"• Item Id: {item.id} - {item.name} - ${item.price:.2f}"

    if item.number:
        text += f" (#{item.number})"

    # Add special indicators
    indicators = []
    if item.is_popular:
        indicators.append("POPULAR")
    if item.is_special:
        indicators.append("SPECIAL")
    if item.is_new:
        indicators.append("NEW")
    if item.is_limited_time:
        indicators.append("LIMITED")

    if indicators:
        text += f" [{', '.join(indicators)}]"

    text += "\n"

    if item.description:
        text += f"  {item.description}\n"

    return text
