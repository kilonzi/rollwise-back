"""
Appointment context builder utility
"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Agent, Event
from app.utils.logging_config import app_logger


def build_appointment_context(
    agent: Agent,
    db_session: Optional[Session] = None,
    caller_phone: Optional[str] = None
) -> str:
    """
    Build appointment booking context with practical function call examples
    and upcoming appointments for the caller
    """
    if not getattr(agent, 'booking_enabled', True) or not agent.calendar_id:
        return ""

    # Extract attendee emails from agent.invitees for realistic examples (team members)
    attendee_emails = []
    attendee_names = []
    if hasattr(agent, 'invitees') and agent.invitees:
        try:
            # agent.invitees is a list of objects like [{"name": "John Doe", "email": "john@example.com", "availability": "always"}]
            attendee_emails = [invitee.get('email') for invitee in agent.invitees if invitee.get('email')]
            attendee_names = [invitee.get('name') for invitee in agent.invitees if invitee.get('name')]
        except (TypeError, AttributeError):
            app_logger.warning(f"Failed to parse agent.invitees for agent {agent.id}")
            attendee_emails = []
            attendee_names = []

    # Format attendees for display - show team member names
    if attendee_names:
        team_members = ', '.join(attendee_names)
    else:
        team_members = "No team members configured"

    appointment_context = f"""
=== APPOINTMENT & RESERVATION BOOKING SYSTEM ===
This system is ONLY for scheduling APPOINTMENTS, RESERVATIONS, and BOOKINGS - NOT for food/product orders!

🏥 APPOINTMENT BOOKING (Medical, Consultation, Service Appointments):
For: Doctor visits, consultations, therapy sessions, professional services, personal meetings

🍽️ RESERVATION BOOKING (Restaurant, Event, Table Bookings):
For: Restaurant tables, event spaces, venue bookings, group dining

⚠️  IMPORTANT: This is NOT for food/product orders! Use order tools for buying items.

AVAILABLE APPOINTMENT/RESERVATION FUNCTIONS WITH EXAMPLES:
Always use agent_id "{agent.id}" for all appointment operations.
Customer's phone: {caller_phone or "[customer_phone]"} (always include in appointments)

1. CREATE_APPOINTMENT - Schedule appointments, reservations, or bookings
   WHEN TO USE: Customer wants to book time, schedule a visit, reserve a table, make an appointment
   
   IMPORTANT: 
   - Summary will be: "Customer Name, Phone Number - Service Type"
   - Attendees are automatically set to team members from agent.invitees
   - Always ask for customer's full name and service type if not provided
   
   Real Examples:
   - "I'd like to book an appointment for tomorrow at 2 PM" (Need to ask for name and service)
     → create_appointment(agent_id="{agent.id}", customer_name="John Smith", start_time="2025-09-30T14:00:00", end_time="2025-09-30T15:00:00", phone_number="{caller_phone or '[customer_phone]'}")
   
   - "I'm John Smith, I need a consultation tomorrow at 2 PM"
     → create_appointment(agent_id="{agent.id}", customer_name="John Smith", service_type="consultation", start_time="2025-09-30T14:00:00", end_time="2025-09-30T15:00:00", phone_number="{caller_phone or '[customer_phone]'}")
   
   - "This is Jane Doe, I'd like to make a dinner reservation for 4 people at 7 PM on Friday"
     → create_appointment(agent_id="{agent.id}", customer_name="Jane Doe", service_type="dinner reservation", start_time="2025-10-03T19:00:00", end_time="2025-10-03T20:30:00", phone_number="{caller_phone or '[customer_phone]'}", description="Table for 4 guests")

2. GET_AVAILABLE_TIMES - Check when appointments/reservations can be scheduled
   WHEN TO USE: Customer asks about availability, open times, when they can book
   
   Examples:
   - "When are you available this week?"
     → get_available_times(agent_id="{agent.id}", date="2025-09-29", days=7, duration_minutes=60)
   
   - "What times do you have open tomorrow for a reservation?"
     → get_available_times(agent_id="{agent.id}", date="2025-09-30", duration_minutes={agent.default_slot_duration or 60})

3. CANCEL_APPOINTMENT - Cancel scheduled appointments/reservations
   WHEN TO USE: Customer wants to cancel their booking
   
   Example:
   - "I need to cancel my appointment"
     → cancel_appointment(event_id="[appointment_id]", reason="customer_request")

4. RESCHEDULE_APPOINTMENT - Move appointments to new times
   WHEN TO USE: Customer wants to change their appointment time
   
   Example:
   - "Can I move my reservation to next Tuesday at 3 PM?"
     → reschedule_appointment(event_id="[appointment_id]", new_start_time="2025-10-01T15:00:00", new_end_time="2025-10-01T16:00:00")

5. GET_UPCOMING_APPOINTMENTS - Check scheduled appointments/reservations
   WHEN TO USE: Customer asks about their bookings
   
   Example:
   - "What reservations do I have this week?"
     → get_upcoming_appointments(agent_id="{agent.id}", start_date="2025-09-29", days=7)

6. ADD_ATTENDEE_TO_APPOINTMENT - Add someone to an existing appointment
   WHEN TO USE: Customer wants to add another person to their appointment
   
   Example:
   - "Add John Smith to my 2 PM appointment"
     → add_attendee_to_appointment(event_id="[appointment_id]", attendee_name="John Smith")

BOOKING CONFIGURATION:
- Default appointment duration: {agent.default_slot_duration or 60} minutes
- Buffer time between slots: {agent.buffer_time or 10} minutes  
- Maximum bookings per slot: {agent.max_slot_appointments or 1}
- Timezone: {agent.timezone or 'UTC'}

TEAM MEMBERS (Automatically added as attendees):
{team_members}

APPOINTMENT SUMMARY FORMAT:
- Format: "Customer Name, Phone Number - Service Type"
- Example: "John Smith, +1234567890 - Consultation"
- Example: "Jane Doe, +1234567890 - Dinner Reservation"

IMPORTANT REMINDERS:
- Always ask for customer's full name if not provided
- Ask for service type/reason for appointment
- Attendees are automatically set to team members (agent.invitees)
- Customer phone number is already captured from the call
"""

    # Add business hours information
    if hasattr(agent, 'business_hours') and agent.business_hours:
        appointment_context += "\nBUSINESS HOURS FOR APPOINTMENTS:"
        for day, hours in agent.business_hours.items():
            if hours.get("enabled", False):
                appointment_context += f"\n- {day.capitalize()}: {hours.get('open', '09:00')}-{hours.get('close', '17:00')}"
            else:
                appointment_context += f"\n- {day.capitalize()}: Closed"

    # Add blocked dates if any
    if hasattr(agent, 'blocked_dates') and agent.blocked_dates:
        appointment_context += f"\n\nUNAVAILABLE DATES: {', '.join(agent.blocked_dates)}"

    # Add upcoming appointments for the caller if we have their phone number and db session
    if db_session and caller_phone:
        upcoming_appointments = _get_caller_upcoming_appointments(
            db_session, agent.id, caller_phone, limit=5
        )

        if upcoming_appointments:
            appointment_context += f"\n\nCUSTOMER'S UPCOMING APPOINTMENTS/RESERVATIONS:"
            for apt in upcoming_appointments:
                # Format datetime for display
                start_time = apt.start_time.strftime("%A, %B %d at %I:%M %p")
                appointment_context += f"\n- ID: {apt.id} | {start_time} | {apt.summary}"
                if apt.description:
                    appointment_context += f" | {apt.description}"

            appointment_context += "\nCustomer can reference these by ID for cancellation or rescheduling."
        else:
            appointment_context += f"\n\nCUSTOMER'S UPCOMING APPOINTMENTS: No upcoming appointments found."

    appointment_context += f"""

🚨 CRITICAL: APPOINTMENT vs ORDER DISTINCTION
- Use APPOINTMENT tools for: scheduling time, booking visits, making reservations, setting up meetings
- Do NOT use appointment tools for: ordering food, buying products, purchasing items
- When customer says "I want to order..." → Use ORDER tools (add_item_to_order, etc.)  
- When customer says "I want to book/schedule/reserve..." → Use APPOINTMENT tools (create_appointment, etc.)

PROCESS: Always check availability with get_available_times BEFORE creating appointments!
"""

    return appointment_context


def _get_caller_upcoming_appointments(
    db_session: Session,
    agent_id: str,
    caller_phone: str,
    limit: int = 5
) -> List[Event]:
    """
    Get upcoming appointments for a specific caller's phone number
    """
    try:
        now = datetime.utcnow()
        appointments = (
            db_session.query(Event)
            .filter(
                Event.agent_id == agent_id,
                Event.phone_number == caller_phone,
                Event.start_time > now,
                Event.status != "cancelled"
            )
            .order_by(Event.start_time)
            .limit(limit)
            .all()
        )
        return appointments
    except Exception as e:
        app_logger.error(f"Error fetching caller appointments: {str(e)}")
        return []
