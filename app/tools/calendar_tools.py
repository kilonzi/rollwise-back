"""
Calendar management tools for appointment booking and scheduling operations.
Provides comprehensive calendar functionality including creating appointments,
checking availability, canceling/rescheduling appointments, and managing attendees.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models import get_db, Event, Agent
from app.services.calendar_service import CalendarService, EventCreateRequest, EventUpdateRequest
from app.tools.registry import tool, global_registry
from app.utils.logging_config import app_logger


@tool(
    name="create_appointment",
    description="""Create a new appointment or booking for the agent.
    Use this function when customers want to book appointments, make reservations, or schedule services.
    
    The summary should include the customer's name and phone number, plus service details if mentioned.
    Attendees are automatically set to the agent's team members from agent.invitees.
    
    Examples:
    - "I'd like to book an appointment for tomorrow at 2 PM" → create_appointment(agent_id="123", customer_name="John Smith", start_time="2024-03-15T14:00:00", end_time="2024-03-15T15:00:00", phone_number="+1234567890")
    - "Can I make a consultation appointment for 3 PM?" → create_appointment(agent_id="123", customer_name="Jane Doe", service_type="consultation", start_time="2024-03-15T15:00:00", end_time="2024-03-15T16:00:00", phone_number="+1234567890")
    """,
    parameters={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent ID to create the appointment for",
            },
            "customer_name": {
                "type": "string",
                "description": "Customer's full name for the appointment",
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO format (e.g., '2024-03-15T14:00:00')",
            },
            "end_time": {
                "type": "string",
                "description": "End time in ISO format (e.g., '2024-03-15T15:00:00')",
            },
            "phone_number": {
                "type": "string",
                "description": "Customer's phone number for the appointment",
            },
            "service_type": {
                "type": "string",
                "description": "Type of service or reason for appointment (optional)",
            },
            "description": {
                "type": "string",
                "description": "Additional details about the appointment",
            },
            "created_by": {
                "type": "string",
                "description": "User ID of who created the appointment",
            },
        },
        "required": ["agent_id", "customer_name", "start_time", "end_time", "phone_number"],
    },
)
async def create_appointment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new appointment/booking for the agent"""
    try:
        agent_id = args.get("agent_id")
        customer_name = args.get("customer_name")
        start_time_str = args.get("start_time")
        end_time_str = args.get("end_time")
        phone_number = args.get("phone_number")
        service_type = args.get("service_type")
        description = args.get("description")
        created_by = args.get("created_by")

        if not all([agent_id, customer_name, start_time_str, end_time_str, phone_number]):
            return {"error": "agent_id, customer_name, start_time, end_time, and phone_number are required"}

        # Parse datetime strings
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
        except ValueError:
            return {"error": "Invalid datetime format. Use ISO format like '2024-03-15T14:00:00'"}

        if start_time >= end_time:
            return {"error": "Start time must be before end time"}

        db: Session = next(get_db())
        try:
            # Find the agent
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"error": f"Agent with ID {agent_id} not found"}

            if not agent.calendar_id:
                return {"error": f"Agent {agent_id} does not have a calendar configured"}

            # Build summary: "Customer Name, Phone Number" + service if mentioned
            summary = f"{customer_name}, {phone_number}"
            if service_type:
                summary += f" - {service_type}"

            # Get attendees from agent.invitees (team members)
            attendees = []
            if hasattr(agent, 'invitees') and agent.invitees:
                try:
                    # Extract emails from agent.invitees for Google Calendar compatibility
                    attendees = [invitee.get('email') for invitee in agent.invitees if invitee.get('email')]
                except (TypeError, AttributeError):
                    app_logger.warning(f"Failed to parse agent.invitees for agent {agent_id}")
                    attendees = []

            # Create the event
            event = Event(
                calendar_id=agent.calendar_id,
                agent_id=agent_id,
                summary=summary,
                description=description,
                start_time=start_time,
                end_time=end_time,
                timezone=agent.timezone or "UTC",
                attendees=attendees,
                created_by=created_by,
                phone_number=phone_number,
            )

            db.add(event)
            db.commit()
            db.refresh(event)

            # Sync with Google Calendar
            calendar_service = CalendarService()
            google_event_req = EventCreateRequest(
                summary=summary,
                start={
                    "dateTime": start_time.isoformat(),
                    "timeZone": agent.timezone or "UTC"
                },
                end={
                    "dateTime": end_time.isoformat(),
                    "timeZone": agent.timezone or "UTC"
                },
                description=description,
                attendees=attendees
            )

            google_event = calendar_service.create_event(agent.calendar_id, google_event_req)

            # Update with Google Calendar event ID if needed
            if google_event.get("id"):
                event.google_event_id = google_event["id"]
                db.commit()

            return {
                "success": True,
                "event_id": event.id,
                "agent_id": agent_id,
                "summary": summary,
                "customer_name": customer_name,
                "phone_number": phone_number,
                "service_type": service_type,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "timezone": agent.timezone or "UTC",
                "duration_minutes": int((end_time - start_time).total_seconds() / 60),
                "attendees": attendees,
                "description": description,
                "google_event_id": google_event.get("id"),
                "message": f"Appointment '{summary}' scheduled for {start_time.strftime('%B %d, %Y at %I:%M %p')}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error creating appointment: {str(e)}")
        return {"error": f"Failed to create appointment: {str(e)}"}


@tool(
    name="get_available_times",
    description="""Check available time slots for booking appointments.
    Use this function when customers ask "When are you available?" or want to see open slots.
    
    This will check the agent's business hours and existing appointments to find free times.
    
    Examples:
    - "When are you available this week?" → get_available_times(agent_id="123", date="2024-03-15")
    - "What times do you have open tomorrow?" → get_available_times(agent_id="123", date="2024-03-16", duration_minutes=60)
    - "Can you check availability for next Monday?" → get_available_times(agent_id="123", date="2024-03-18")
    """,
    parameters={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent ID to check availability for",
            },
            "date": {
                "type": "string",
                "description": "Date to check availability (YYYY-MM-DD format)",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Duration of appointment needed in minutes",
                "default": 60,
                "minimum": 15,
            },
            "days": {
                "type": "integer",
                "description": "Number of days to check from the given date",
                "default": 7,
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": ["agent_id", "date"],
    },
)
async def get_available_times(args: Dict[str, Any]) -> Dict[str, Any]:
    """Check available time slots for the agent"""
    try:
        agent_id = args.get("agent_id")
        date_str = args.get("date")
        duration_minutes = args.get("duration_minutes", 60)
        days = args.get("days", 7)

        if not all([agent_id, date_str]):
            return {"error": "agent_id and date are required"}

        # Parse date
        try:
            check_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD format"}

        db: Session = next(get_db())
        try:
            # Find the agent
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"error": f"Agent with ID {agent_id} not found"}

            available_slots = []

            # Check each day
            for day_offset in range(days):
                current_date = check_date + timedelta(days=day_offset)
                day_name = current_date.strftime("%a").lower()  # mon, tue, etc.

                # Check if agent has business hours for this day
                business_hours = agent.business_hours or {}
                day_hours = business_hours.get(day_name[:3], {})  # mon, tue, wed

                if not day_hours.get("enabled", False):
                    continue

                open_time = day_hours.get("open", "09:00")
                close_time = day_hours.get("close", "17:00")

                # Convert to datetime objects
                open_datetime = datetime.combine(current_date, datetime.strptime(open_time, "%H:%M").time())
                close_datetime = datetime.combine(current_date, datetime.strptime(close_time, "%H:%M").time())

                # Get existing appointments for this day
                existing_events = (
                    db.query(Event)
                    .filter(
                        Event.agent_id == agent_id,
                        Event.active == True,
                        Event.start_time >= open_datetime,
                        Event.start_time < close_datetime + timedelta(days=1)
                    )
                    .order_by(Event.start_time)
                    .all()
                )

                # Find available slots
                current_time = open_datetime
                day_slots = []

                while current_time + timedelta(minutes=duration_minutes) <= close_datetime:
                    slot_end = current_time + timedelta(minutes=duration_minutes)

                    # Check if this slot conflicts with existing appointments
                    conflict = False
                    for event in existing_events:
                        if (current_time < event.end_time and slot_end > event.start_time):
                            conflict = True
                            break

                    if not conflict:
                        day_slots.append({
                            "start_time": current_time.isoformat(),
                            "end_time": slot_end.isoformat(),
                            "formatted_time": current_time.strftime("%I:%M %p"),
                            "date": current_date.strftime("%Y-%m-%d"),
                            "day_name": current_date.strftime("%A"),
                        })

                    # Move to next slot (15-minute intervals)
                    current_time += timedelta(minutes=15)

                if day_slots:
                    available_slots.extend(day_slots)

            return {
                "success": True,
                "agent_id": agent_id,
                "checked_dates": f"{check_date} to {check_date + timedelta(days=days-1)}",
                "duration_minutes": duration_minutes,
                "available_slots": available_slots[:20],  # Limit to 20 slots
                "total_slots_found": len(available_slots),
                "message": f"Found {len(available_slots)} available time slots of {duration_minutes} minutes each",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error checking available times: {str(e)}")
        return {"error": f"Failed to check available times: {str(e)}"}


@tool(
    name="cancel_appointment",
    description="""Cancel an existing appointment or booking.
    Use this function when customers want to cancel their appointments.
    
    Examples:
    - "I need to cancel my appointment" → cancel_appointment(event_id="123")
    - "Can you cancel my reservation for tomorrow?" → cancel_appointment(event_id="456", reason="customer_request")
    """,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The event/appointment ID to cancel",
            },
            "reason": {
                "type": "string",
                "description": "Reason for cancellation",
                "enum": [
                    "customer_request",
                    "business_closure",
                    "emergency",
                    "reschedule",
                    "other",
                ],
                "default": "customer_request",
            },
        },
        "required": ["event_id"],
    },
)
async def cancel_appointment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel an existing appointment"""
    try:
        event_id = args.get("event_id")
        reason = args.get("reason", "customer_request")

        if not event_id:
            return {"error": "event_id is required"}

        db: Session = next(get_db())
        try:
            # Find the event
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                return {"error": f"Appointment with ID {event_id} not found"}

            if not event.active:
                return {"error": f"Appointment {event_id} is already cancelled"}

            # Check if appointment is in the past
            if event.start_time < datetime.utcnow():
                return {"error": "Cannot cancel appointments that have already started or passed"}

            # Cancel the event
            event.active = False
            event.cancelled_at = datetime.utcnow()
            event.cancellation_reason = reason
            event.updated_at = datetime.utcnow()

            db.commit()

            # Cancel in Google Calendar if synced
            if hasattr(event, 'google_event_id') and event.google_event_id:
                try:
                    calendar_service = CalendarService()
                    calendar_service.delete_event(event.calendar_id, event.google_event_id)
                except Exception as sync_error:
                    app_logger.warning(f"Failed to cancel Google Calendar event: {sync_error}")

            return {
                "success": True,
                "event_id": event_id,
                "summary": event.summary,
                "original_start_time": event.start_time.isoformat(),
                "original_end_time": event.end_time.isoformat(),
                "cancellation_reason": reason,
                "cancelled_at": event.cancelled_at.isoformat(),
                "attendees": event.attendees or [],
                "message": f"Appointment '{event.summary}' scheduled for {event.start_time.strftime('%B %d, %Y at %I:%M %p')} has been cancelled",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error cancelling appointment: {str(e)}")
        return {"error": f"Failed to cancel appointment: {str(e)}"}


@tool(
    name="reschedule_appointment",
    description="""Reschedule an existing appointment to a new time.
    Use this function when customers want to move their appointment to a different time.
    
    Examples:
    - "Can I move my appointment to next Tuesday at 3 PM?" → reschedule_appointment(event_id="123", new_start_time="2024-03-19T15:00:00", new_end_time="2024-03-19T16:00:00")
    - "I need to reschedule for tomorrow instead" → reschedule_appointment(event_id="456", new_start_time="2024-03-16T14:00:00", new_end_time="2024-03-16T15:00:00")
    """,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The event/appointment ID to reschedule",
            },
            "new_start_time": {
                "type": "string",
                "description": "New start time in ISO format (e.g., '2024-03-15T14:00:00')",
            },
            "new_end_time": {
                "type": "string",
                "description": "New end time in ISO format (e.g., '2024-03-15T15:00:00')",
            },
        },
        "required": ["event_id", "new_start_time", "new_end_time"],
    },
)
async def reschedule_appointment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Reschedule an existing appointment to a new time"""
    try:
        event_id = args.get("event_id")
        new_start_time_str = args.get("new_start_time")
        new_end_time_str = args.get("new_end_time")

        if not all([event_id, new_start_time_str, new_end_time_str]):
            return {"error": "event_id, new_start_time, and new_end_time are required"}

        # Parse datetime strings
        try:
            new_start_time = datetime.fromisoformat(new_start_time_str.replace("Z", "+00:00"))
            new_end_time = datetime.fromisoformat(new_end_time_str.replace("Z", "+00:00"))
        except ValueError:
            return {"error": "Invalid datetime format. Use ISO format like '2024-03-15T14:00:00'"}

        if new_start_time >= new_end_time:
            return {"error": "New start time must be before new end time"}

        db: Session = next(get_db())
        try:
            # Find the event
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                return {"error": f"Appointment with ID {event_id} not found"}

            if not event.active:
                return {"error": f"Cannot reschedule cancelled appointment {event_id}"}

            # Store original times for response
            original_start = event.start_time
            original_end = event.end_time

            # Update the event
            event.start_time = new_start_time
            event.end_time = new_end_time
            event.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(event)

            # Update in Google Calendar if synced
            if hasattr(event, 'google_event_id') and event.google_event_id:
                try:
                    calendar_service = CalendarService()
                    update_req = EventUpdateRequest(
                        start={
                            "dateTime": new_start_time.isoformat(),
                            "timeZone": event.timezone
                        },
                        end={
                            "dateTime": new_end_time.isoformat(),
                            "timeZone": event.timezone
                        }
                    )
                    calendar_service.update_event(event.calendar_id, event.google_event_id, update_req)
                except Exception as sync_error:
                    app_logger.warning(f"Failed to update Google Calendar event: {sync_error}")

            return {
                "success": True,
                "event_id": event_id,
                "summary": event.summary,
                "original_start_time": original_start.isoformat(),
                "original_end_time": original_end.isoformat(),
                "new_start_time": new_start_time.isoformat(),
                "new_end_time": new_end_time.isoformat(),
                "timezone": event.timezone,
                "attendees": event.attendees or [],
                "message": f"Appointment '{event.summary}' rescheduled from {original_start.strftime('%B %d, %Y at %I:%M %p')} to {new_start_time.strftime('%B %d, %Y at %I:%M %p')}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error rescheduling appointment: {str(e)}")
        return {"error": f"Failed to reschedule appointment: {str(e)}"}


@tool(
    name="get_upcoming_appointments",
    description="""Get list of upcoming appointments for the agent.
    Use this function to check what appointments are scheduled.
    
    Examples:
    - "What appointments do I have today?" → get_upcoming_appointments(agent_id="123", days=1)
    - "Show me this week's bookings" → get_upcoming_appointments(agent_id="123", days=7)
    - "What's my schedule for tomorrow?" → get_upcoming_appointments(agent_id="123", start_date="2024-03-16", days=1)
    """,
    parameters={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent ID to get appointments for",
            },
            "start_date": {
                "type": "string",
                "description": "Start date to check from (YYYY-MM-DD format). Defaults to today.",
            },
            "days": {
                "type": "integer",
                "description": "Number of days to check from start date",
                "default": 7,
                "minimum": 1,
                "maximum": 30,
            },
            "active_only": {
                "type": "boolean",
                "description": "Only return active (non-cancelled) appointments",
                "default": True,
            },
        },
        "required": ["agent_id"],
    },
)
async def get_upcoming_appointments(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get upcoming appointments for the agent"""
    try:
        agent_id = args.get("agent_id")
        start_date_str = args.get("start_date")
        days = args.get("days", 7)
        active_only = args.get("active_only", True)

        if not agent_id:
            return {"error": "agent_id is required"}

        # Parse start date or use today
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            except ValueError:
                return {"error": "Invalid start_date format. Use YYYY-MM-DD format"}
        else:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        end_date = start_date + timedelta(days=days)

        db: Session = next(get_db())
        try:
            # Build query
            query = db.query(Event).filter(
                Event.agent_id == agent_id,
                Event.start_time >= start_date,
                Event.start_time < end_date
            )

            if active_only:
                query = query.filter(Event.active == True)

            appointments = query.order_by(Event.start_time).all()

            appointments_list = []
            for appointment in appointments:
                appointment_data = {
                    "event_id": appointment.id,
                    "summary": appointment.summary,
                    "description": appointment.description,
                    "start_time": appointment.start_time.isoformat(),
                    "end_time": appointment.end_time.isoformat(),
                    "formatted_start": appointment.start_time.strftime("%B %d, %Y at %I:%M %p"),
                    "formatted_end": appointment.end_time.strftime("%I:%M %p"),
                    "timezone": appointment.timezone,
                    "phone_number": appointment.phone_number,
                    "duration_minutes": int((appointment.end_time - appointment.start_time).total_seconds() / 60),
                    "attendees": appointment.attendees or [],
                    "active": appointment.active,
                    "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
                }
                appointments_list.append(appointment_data)

            return {
                "success": True,
                "agent_id": agent_id,
                "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "appointments": appointments_list,
                "total_found": len(appointments_list),
                "active_only": active_only,
                "message": f"Found {len(appointments_list)} appointment(s) for the specified period",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error getting upcoming appointments: {str(e)}")
        return {"error": f"Failed to get upcoming appointments: {str(e)}"}


@tool(
    name="add_attendee_to_appointment",
    description="""Add an attendee to an existing appointment.
    Use this function when someone needs to be added to an appointment.
    
    Examples:
    - "Add John Smith to my 2 PM appointment" → add_attendee_to_appointment(event_id="123", attendee_name="John Smith")
    - "Can you add my partner Sarah Johnson to the reservation?" → add_attendee_to_appointment(event_id="456", attendee_name="Sarah Johnson")
    """,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The event/appointment ID to add attendee to",
            },
            "attendee_name": {
                "type": "string",
                "description": "Full name of the attendee to add",
            },
        },
        "required": ["event_id", "attendee_name"],
    },
)
async def add_attendee_to_appointment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add an attendee to an existing appointment"""
    try:
        event_id = args.get("event_id")
        attendee_name = args.get("attendee_name")

        if not all([event_id, attendee_name]):
            return {"error": "event_id and attendee_name are required"}

        db: Session = next(get_db())
        try:
            # Find the event
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                return {"error": f"Appointment with ID {event_id} not found"}

            if not event.active:
                return {"error": f"Cannot add attendees to cancelled appointment {event_id}"}

            # Get current attendees (assuming they're stored as names now)
            attendees = event.attendees or []

            if attendee_name in attendees:
                return {"error": f"Attendee {attendee_name} is already added to this appointment"}

            # Add the new attendee
            attendees.append(attendee_name)
            event.attendees = attendees
            event.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(event)

            # Update in Google Calendar if synced
            if hasattr(event, 'google_event_id') and event.google_event_id:
                try:
                    calendar_service = CalendarService()
                    # For Google Calendar, we might need to convert names to emails if available
                    # or handle this differently based on your Google Calendar integration needs
                    update_req = EventUpdateRequest(attendees=attendees)
                    calendar_service.update_event(event.calendar_id, event.google_event_id, update_req)
                except Exception as sync_error:
                    app_logger.warning(f"Failed to update Google Calendar attendees: {sync_error}")

            return {
                "success": True,
                "event_id": event_id,
                "summary": event.summary,
                "added_attendee": attendee_name,
                "all_attendees": attendees,
                "total_attendees": len(attendees),
                "appointment_time": event.start_time.strftime("%B %d, %Y at %I:%M %p"),
                "message": f"Added {attendee_name} to appointment '{event.summary}' on {event.start_time.strftime('%B %d, %Y at %I:%M %p')}",
            }

        finally:
            db.close()

    except Exception as e:
        app_logger.error(f"Error adding attendee to appointment: {str(e)}")
        return {"error": f"Failed to add attendee to appointment: {str(e)}"}


# Register all calendar tools
tools_to_register = [
    create_appointment,
    get_available_times,
    cancel_appointment,
    reschedule_appointment,
    get_upcoming_appointments,
    add_attendee_to_appointment,
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
