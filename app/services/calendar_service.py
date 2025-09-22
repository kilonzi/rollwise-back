import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config.settings import settings
from app.models import Agent
from app.utils.logging_config import app_logger


class CalendarService:
    """Service for managing Google Calendar integration per agent"""

    def __init__(self):
        self.credentials = None
        self.service = None
        self._initialize_service()

    def _initialize_service(self):
        """Initialize Google Calendar service with domain-wide delegation"""
        try:
            # Load service account credentials
            credentials_path = settings.GOOGLE_CALENDAR_CREDENTIALS_PATH
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Google Calendar credentials file not found: {credentials_path}"
                )

            with open(credentials_path, "r") as f:
                credentials_info = json.load(f)

            # Create credentials with domain-wide delegation
            self.credentials = service_account.Credentials.from_service_account_info(
                credentials_info, scopes=["https://www.googleapis.com/auth/calendar"]
            )

            # For domain-wide delegation, delegate to the domain admin
            if settings.GOOGLE_CALENDAR_DOMAIN:
                self.credentials = self.credentials.with_subject(
                    f"jkitonyo@{settings.GOOGLE_CALENDAR_DOMAIN}"
                )

            # Build the Calendar service
            self.service = build("calendar", "v3", credentials=self.credentials)
            app_logger.info("Google Calendar service initialized successfully")

        except Exception as e:
            app_logger.error(f"Failed to initialize Google Calendar service: {str(e)}")
            raise

    def create_agent_calendar(self, agent_id: str, agent_name: str) -> str:
        """Create a dedicated calendar for an agent and return calendar ID"""
        try:
            calendar_body = {
                "summary": f"Agent {agent_name} ({agent_id})",
                "description": f"Calendar for AI agent {agent_name}",
                "timeZone": "UTC",
            }

            created_calendar = (
                self.service.calendars().insert(body=calendar_body).execute()
            )
            calendar_id = created_calendar["id"]

            app_logger.info(f"Created calendar for agent {agent_id}: {calendar_id}")
            return calendar_id

        except HttpError as e:
            app_logger.error(
                f"Failed to create calendar for agent {agent_id}: {str(e)}"
            )
            raise

    def get_available_slots(
        self,
        agent: Agent,
        start_date: datetime,
        end_date: datetime,
        slot_duration: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find available time slots for an agent within a date range"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        slot_duration = slot_duration or agent.default_slot_duration
        business_hours = agent.business_hours or {
            "start": "09:00",
            "end": "17:00",
            "timezone": "UTC",
            "days": [1, 2, 3, 4, 5],
        }

        try:
            # Get existing events
            events_result = (
                self.service.events()
                .list(
                    calendarId=agent.calendar_id,
                    timeMin=start_date.isoformat() + "Z",
                    timeMax=end_date.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            existing_events = events_result.get("items", [])

            # Generate available slots
            available_slots = []
            current_date = start_date.date()
            end_date_only = end_date.date()

            while current_date <= end_date_only:
                # Check if day is in business days
                if current_date.weekday() + 1 in business_hours["days"]:
                    day_slots = self._generate_day_slots(
                        current_date,
                        business_hours,
                        slot_duration,
                        agent.buffer_time,
                        existing_events,
                    )
                    available_slots.extend(day_slots)

                current_date += timedelta(days=1)

            # Limit to max slot appointments (prevent overbooking)
            return self._limit_slot_appointments(
                available_slots, agent.max_slot_appointments
            )

        except HttpError as e:
            app_logger.error(
                f"Failed to get available slots for agent {agent.id}: {str(e)}"
            )
            raise

    def _generate_day_slots(
        self,
        date: datetime.date,
        business_hours: Dict[str, Any],
        slot_duration: int,
        buffer_time: int,
        existing_events: List[Dict],
    ) -> List[Dict[str, Any]]:
        """Generate available slots for a specific day"""
        slots = []

        # Parse business hours
        start_time = datetime.strptime(business_hours["start"], "%H:%M").time()
        end_time = datetime.strptime(business_hours["end"], "%H:%M").time()

        # Create datetime objects for the day
        current_slot = datetime.combine(date, start_time)
        end_datetime = datetime.combine(date, end_time)

        # Filter events for this day
        day_events = []
        for event in existing_events:
            event_start = datetime.fromisoformat(
                event["start"]["dateTime"].replace("Z", "+00:00")
            )
            if event_start.date() == date and event.get("status") != "cancelled":
                day_events.append(
                    {
                        "start": event_start,
                        "end": datetime.fromisoformat(
                            event["end"]["dateTime"].replace("Z", "+00:00")
                        ),
                    }
                )

        # Sort events by start time
        day_events.sort(key=lambda x: x["start"])

        # Generate slots avoiding conflicts
        while current_slot + timedelta(minutes=slot_duration) <= end_datetime:
            slot_end = current_slot + timedelta(minutes=slot_duration)

            # Check for conflicts with existing events
            has_conflict = False
            for event in day_events:
                # Check if slot conflicts with event (including buffer time)
                slot_start_with_buffer = current_slot - timedelta(minutes=buffer_time)
                slot_end_with_buffer = slot_end + timedelta(minutes=buffer_time)

                if (
                    slot_start_with_buffer < event["end"]
                    and slot_end_with_buffer > event["start"]
                ):
                    has_conflict = True
                    break

            if not has_conflict:
                slots.append(
                    {
                        "start": current_slot.isoformat(),
                        "end": slot_end.isoformat(),
                        "duration_minutes": slot_duration,
                    }
                )

            # Move to next slot
            current_slot += timedelta(minutes=slot_duration)

        return slots

    def _limit_slot_appointments(
        self, slots: List[Dict[str, Any]], max_per_slot: int
    ) -> List[Dict[str, Any]]:
        """Limit appointments per time slot to prevent overbooking"""
        if max_per_slot is None or max_per_slot <= 0:
            return slots

        # For now, if max_per_slot is 1, we've already filtered out overlapping slots
        # This method can be enhanced later to handle multiple appointments per slot
        # by checking existing appointments for each time slot

        return slots

    def create_event(
        self,
        agent: Agent,
        summary: str,
        start_datetime: datetime,
        end_datetime: datetime,
        client_name: Optional[str] = None,
        client_phone: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event with validation"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        # Validate business hours
        if not self._is_within_business_hours(agent, start_datetime, end_datetime):
            raise ValueError("Event time is outside business hours")

        # Check for conflicts
        if not self._is_slot_available(agent, start_datetime, end_datetime):
            # Get alternative slots
            alternatives = self.get_available_slots(
                agent,
                start_datetime - timedelta(days=1),
                start_datetime + timedelta(days=7),
                int((end_datetime - start_datetime).total_seconds() / 60),
            )
            raise ValueError(
                f"Time slot conflicts with existing event. Suggested alternatives: {alternatives[:5]}"
            )

        try:
            # Build event description
            event_description = description or ""
            if client_name:
                event_description += f"\nClient: {client_name}"
            if client_phone:
                event_description += f"\nPhone: {client_phone}"

            # Build attendees list
            attendee_list = []
            if attendees:
                attendee_list = [{"email": email} for email in attendees]

            event_body = {
                "summary": summary,
                "description": event_description.strip(),
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end_datetime.isoformat(),
                    "timeZone": "UTC",
                },
                "attendees": attendee_list,
                "location": location,
                "extendedProperties": {
                    "private": {
                        "agent_id": agent.id,
                        "client_phone": client_phone or "",
                        "client_name": client_name or "",
                    }
                },
            }

            if location:
                event_body["location"] = location

            created_event = (
                self.service.events()
                .insert(calendarId=agent.calendar_id, body=event_body)
                .execute()
            )

            app_logger.info(f"Created event {created_event['id']} for agent {agent.id}")
            return created_event

        except HttpError as e:
            app_logger.error(f"Failed to create event for agent {agent.id}: {str(e)}")
            raise

    def _is_within_business_hours(
        self, agent: Agent, start_dt: datetime, end_dt: datetime
    ) -> bool:
        """Check if event time is within agent's business hours"""
        business_hours = agent.business_hours or {
            "start": "09:00",
            "end": "17:00",
            "timezone": "UTC",
            "days": [1, 2, 3, 4, 5],
        }

        # Check day of week
        if start_dt.weekday() + 1 not in business_hours["days"]:
            return False

        # Check time
        start_time = datetime.strptime(business_hours["start"], "%H:%M").time()
        end_time = datetime.strptime(business_hours["end"], "%H:%M").time()

        return (
            start_time <= start_dt.time() <= end_time
            and start_time <= end_dt.time() <= end_time
        )

    def _is_slot_available(
        self, agent: Agent, start_dt: datetime, end_dt: datetime
    ) -> bool:
        """Check if a time slot is available (no conflicts with buffer time)"""
        try:
            buffer_minutes = agent.buffer_time or 15

            # Check for events in the buffer window
            check_start = start_dt - timedelta(minutes=buffer_minutes)
            check_end = end_dt + timedelta(minutes=buffer_minutes)

            events_result = (
                self.service.events()
                .list(
                    calendarId=agent.calendar_id,
                    timeMin=check_start.isoformat() + "Z",
                    timeMax=check_end.isoformat() + "Z",
                    singleEvents=True,
                )
                .execute()
            )

            existing_events = events_result.get("items", [])

            # Check for conflicts
            for event in existing_events:
                if event.get("status") == "cancelled":
                    continue

                event_start = datetime.fromisoformat(
                    event["start"]["dateTime"].replace("Z", "+00:00")
                )
                event_end = datetime.fromisoformat(
                    event["end"]["dateTime"].replace("Z", "+00:00")
                )

                # Check overlap
                if start_dt < event_end and end_dt > event_start:
                    return False

            return True

        except HttpError as e:
            app_logger.error(f"Failed to check slot availability: {str(e)}")
            return False

    def cancel_event(self, agent: Agent, event_id: str) -> bool:
        """Cancel (mark as cancelled) an event"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        try:
            # Get the event first
            event = (
                self.service.events()
                .get(calendarId=agent.calendar_id, eventId=event_id)
                .execute()
            )

            # Mark as cancelled
            event["status"] = "cancelled"

            self.service.events().update(
                calendarId=agent.calendar_id, eventId=event_id, body=event
            ).execute()

            app_logger.info(f"Cancelled event {event_id} for agent {agent.id}")
            return True

        except HttpError as e:
            app_logger.error(f"Failed to cancel event {event_id}: {str(e)}")
            return False

    def search_events(
        self,
        agent: Agent,
        start_date: datetime,
        end_date: datetime,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for events in agent's calendar"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=agent.calendar_id,
                    timeMin=start_date.isoformat() + "Z",
                    timeMax=end_date.isoformat() + "Z",
                    q=query,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            return events_result.get("items", [])

        except HttpError as e:
            app_logger.error(f"Failed to search events for agent {agent.id}: {str(e)}")
            raise

    def update_event(
        self, agent: Agent, event_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing event"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        try:
            # Get the current event
            current_event = (
                self.service.events()
                .get(calendarId=agent.calendar_id, eventId=event_id)
                .execute()
            )

            # Apply updates while preserving extended properties
            for key, value in updates.items():
                if key in [
                    "summary",
                    "description",
                    "location",
                    "start",
                    "end",
                    "attendees",
                ]:
                    current_event[key] = value

            # If updating time, validate business hours and conflicts
            if "start" in updates or "end" in updates:
                start_dt = datetime.fromisoformat(
                    current_event["start"]["dateTime"].replace("Z", "+00:00")
                )
                end_dt = datetime.fromisoformat(
                    current_event["end"]["dateTime"].replace("Z", "+00:00")
                )

                if not self._is_within_business_hours(agent, start_dt, end_dt):
                    raise ValueError("Updated time is outside business hours")

            updated_event = (
                self.service.events()
                .update(
                    calendarId=agent.calendar_id, eventId=event_id, body=current_event
                )
                .execute()
            )

            app_logger.info(f"Updated event {event_id} for agent {agent.id}")
            return updated_event

        except HttpError as e:
            app_logger.error(f"Failed to update event {event_id}: {str(e)}")
            raise

    def list_events(
        self,
        agent: Agent,
        start_date: datetime,
        end_date: datetime,
        include_cancelled: bool = False,
    ) -> List[Dict[str, Any]]:
        """List events for a date range"""
        if not agent.calendar_id:
            raise ValueError(f"Agent {agent.id} does not have a calendar configured")

        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=agent.calendar_id,
                    timeMin=start_date.isoformat() + "Z",
                    timeMax=end_date.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                    showDeleted=include_cancelled,
                )
                .execute()
            )

            events = events_result.get("items", [])

            if not include_cancelled:
                events = [e for e in events if e.get("status") != "cancelled"]

            return events

        except HttpError as e:
            app_logger.error(f"Failed to list events for agent {agent.id}: {str(e)}")
            raise
