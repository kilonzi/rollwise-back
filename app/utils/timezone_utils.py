"""
Timezone utilities for agent-specific time handling.

Provides functions to get current time, check business hours, and format dates
in the agent's local timezone for better contextual awareness.
"""

from datetime import datetime, time
from typing import Dict, Any, Optional, Tuple
import pytz
from zoneinfo import ZoneInfo

from app.utils.logging_config import app_logger as logger


def get_agent_timezone(agent_timezone: str) -> pytz.BaseTzInfo:
    """Get timezone object from agent's timezone string"""
    try:
        return pytz.timezone(agent_timezone)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone: {agent_timezone}, falling back to UTC")
        return pytz.UTC


def get_current_time_for_agent(agent_timezone: str) -> datetime:
    """Get current time in agent's timezone"""
    tz = get_agent_timezone(agent_timezone)
    return datetime.now(tz)


def format_agent_datetime(
    dt: datetime, agent_timezone: str, format_str: str = "%Y-%m-%d %H:%M:%S %Z"
) -> str:
    """Format datetime in agent's timezone"""
    tz = get_agent_timezone(agent_timezone)
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.UTC.localize(dt)

    agent_dt = dt.astimezone(tz)
    return agent_dt.strftime(format_str)


def get_current_day_and_time(agent_timezone: str) -> Tuple[str, str, str]:
    """Get current day name, time, and formatted datetime for agent"""
    current_time = get_current_time_for_agent(agent_timezone)

    day_name = current_time.strftime("%A").lower()[:3]  # mon, tue, wed, etc.
    current_time_str = current_time.strftime("%H:%M")
    formatted_datetime = current_time.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    return day_name, current_time_str, formatted_datetime


def is_within_business_hours(
    agent_timezone: str, business_hours: Dict[str, Any]
) -> bool:
    """Check if current time is within business hours"""
    try:
        day_name, current_time_str, _ = get_current_day_and_time(agent_timezone)

        # Get business hours for current day
        day_hours = business_hours.get(day_name, {})

        if not day_hours.get("enabled", False):
            return False

        open_time = day_hours.get("open", "")
        close_time = day_hours.get("close", "")

        if not open_time or not close_time:
            return False

        # Parse times
        current_time = datetime.strptime(current_time_str, "%H:%M").time()
        open_time_obj = datetime.strptime(open_time, "%H:%M").time()
        close_time_obj = datetime.strptime(close_time, "%H:%M").time()

        # Check if current time is within business hours
        if open_time_obj <= close_time_obj:
            # Normal case: open 09:00, close 17:00
            return open_time_obj <= current_time <= close_time_obj
        else:
            # Overnight case: open 22:00, close 06:00
            return current_time >= open_time_obj or current_time <= close_time_obj

    except Exception as e:
        logger.error(f"Error checking business hours: {e}")
        return True  # Default to open if there's an error


def get_business_status(
    agent_timezone: str, business_hours: Dict[str, Any]
) -> Dict[str, Any]:
    """Get comprehensive business status information"""
    day_name, current_time_str, formatted_datetime = get_current_day_and_time(
        agent_timezone
    )
    is_open = is_within_business_hours(agent_timezone, business_hours)

    # Get today's hours
    today_hours = business_hours.get(day_name, {})

    status = {
        "is_open": is_open,
        "current_time": current_time_str,
        "current_day": day_name,
        "formatted_datetime": formatted_datetime,
        "today_enabled": today_hours.get("enabled", False),
        "today_open": today_hours.get("open", ""),
        "today_close": today_hours.get("close", ""),
        "timezone": agent_timezone,
    }

    return status


def get_next_opening_time(
    agent_timezone: str, business_hours: Dict[str, Any]
) -> Optional[str]:
    """Get the next opening time if currently closed"""
    try:
        current_time = get_current_time_for_agent(agent_timezone)

        # Check next 7 days
        for days_ahead in range(8):
            check_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            if days_ahead > 0:
                from datetime import timedelta

                check_date += timedelta(days=days_ahead)

            day_name = check_date.strftime("%A").lower()[:3]
            day_hours = business_hours.get(day_name, {})

            if day_hours.get("enabled", False):
                open_time = day_hours.get("open", "")
                if open_time:
                    # If it's today, check if we're before opening time
                    if days_ahead == 0:
                        open_datetime = current_time.replace(
                            hour=int(open_time.split(":")[0]),
                            minute=int(open_time.split(":")[1]),
                            second=0,
                            microsecond=0,
                        )
                        if current_time < open_datetime:
                            return f"Today at {open_time}"
                    else:
                        day_name_full = check_date.strftime("%A")
                        return f"{day_name_full} at {open_time}"

        return None

    except Exception as e:
        logger.error(f"Error getting next opening time: {e}")
        return None


def build_time_context_for_agent(
    agent_timezone: str, business_hours: Dict[str, Any]
) -> Dict[str, Any]:
    """Build comprehensive time context for agent configuration"""
    business_status = get_business_status(agent_timezone, business_hours)

    context = {
        "current_datetime": business_status["formatted_datetime"],
        "current_time": business_status["current_time"],
        "current_day": business_status["current_day"],
        "timezone": agent_timezone,
        "business_status": {
            "is_open": business_status["is_open"],
            "today_hours": {
                "enabled": business_status["today_enabled"],
                "open": business_status["today_open"],
                "close": business_status["today_close"],
            },
        },
    }

    # Add next opening time if closed
    if not business_status["is_open"]:
        next_opening = get_next_opening_time(agent_timezone, business_hours)
        if next_opening:
            context["business_status"]["next_opening"] = next_opening

    return context
