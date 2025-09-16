"""
Calendar Tools for AI Agent Integration
Provides 5 calendar management functions exposed to the AI model
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from app.services.calendar_service import CalendarService
from app.models import Agent
from app.utils.logging_config import app_logger


class CalendarTools:
    """Calendar tools exposed to AI agents"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.calendar_service = CalendarService()

    def create_calendar_event(self,
                            agent_id: str,
                            summary: str,
                            start_datetime: str,  # ISO format
                            duration_minutes: int = 30,
                            client_name: Optional[str] = None,
                            client_phone: Optional[str] = None,
                            attendees: Optional[List[str]] = None,
                            description: Optional[str] = None,
                            location: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a calendar event/booking for the agent

        Args:
            agent_id: The agent's ID
            summary: Event title/summary
            start_datetime: Start time in ISO format (e.g., "2024-01-15T14:00:00")
            duration_minutes: Event duration in minutes (default: 30)
            client_name: Client's name (optional)
            client_phone: Client's phone number (required if provided)
            attendees: List of attendee email addresses (will be merged with agent's default invitees)
            description: Event description
            location: Event location

        Returns:
            Dict with success status and event details or error message

        Note:
            Default invitees from the agent's settings will automatically be included
            in all calendar events, in addition to any specific attendees provided.
        """
        try:
            # Get agent
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            if not agent.calendar_id:
                return {"success": False, "error": "Agent does not have a calendar configured"}

            if not agent.booking_enabled:
                return {"success": False, "error": "Calendar booking is disabled for this agent"}

            # Parse datetime
            start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            # Before booking, check available slots
            available_slots = self.calendar_service.get_available_slots(
                agent, start_dt, start_dt + timedelta(hours=1), duration_minutes
            )

            # Check if requested slot is available
            requested_slot_available = any(
                datetime.fromisoformat(slot['start']) <= start_dt < datetime.fromisoformat(slot['end'])
                for slot in available_slots
            )

            if not requested_slot_available:
                # Get alternative slots for the day and next few days
                alternatives = self.calendar_service.get_available_slots(
                    agent,
                    start_dt.replace(hour=0, minute=0, second=0),
                    start_dt + timedelta(days=7),
                    duration_minutes
                )[:5]  # Limit to 5 suggestions

                return {
                    "success": False,
                    "error": "Requested time slot is not available",
                    "suggested_alternatives": [
                        {
                            "start": slot['start'],
                            "end": slot['end'],
                            "duration_minutes": slot['duration_minutes']
                        }
                        for slot in alternatives
                    ]
                }

            # Merge default invitees with specific attendees
            all_attendees = []

            # Add default invitees from agent settings
            if agent.invitees:
                for invitee in agent.invitees:
                    if invitee.get("email"):
                        all_attendees.append(invitee["email"])

            # Add specific attendees for this event
            if attendees:
                all_attendees.extend(attendees)

            # Remove duplicates while preserving order
            unique_attendees = []
            seen = set()
            for email in all_attendees:
                if email not in seen:
                    unique_attendees.append(email)
                    seen.add(email)

            # Create the event
            created_event = self.calendar_service.create_event(
                agent=agent,
                summary=summary,
                start_datetime=start_dt,
                end_datetime=end_dt,
                client_name=client_name,
                client_phone=client_phone,
                attendees=unique_attendees,
                description=description,
                location=location
            )

            app_logger.info(f"Created calendar event {created_event['id']} for agent {agent_id}")

            return {
                "success": True,
                "event_id": created_event['id'],
                "summary": created_event['summary'],
                "start": created_event['start']['dateTime'],
                "end": created_event['end']['dateTime'],
                "location": created_event.get('location'),
                "attendees": [a.get('email') for a in created_event.get('attendees', [])],
                "client_info": {
                    "name": client_name,
                    "phone": client_phone
                }
            }

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            app_logger.error(f"Error creating calendar event: {str(e)}")
            return {"success": False, "error": "Failed to create calendar event"}

    def cancel_calendar_event(self, agent_id: str, event_id: str) -> Dict[str, Any]:
        """
        Cancel/remove a calendar event (marks as cancelled)

        Args:
            agent_id: The agent's ID
            event_id: The Google Calendar event ID

        Returns:
            Dict with success status and message
        """
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            if not agent.booking_enabled:
                return {"success": False, "error": "Calendar booking is disabled for this agent"}

            success = self.calendar_service.cancel_event(agent, event_id)

            if success:
                app_logger.info(f"Cancelled event {event_id} for agent {agent_id}")
                return {"success": True, "message": "Event cancelled successfully"}
            else:
                return {"success": False, "error": "Failed to cancel event"}

        except Exception as e:
            app_logger.error(f"Error cancelling event {event_id}: {str(e)}")
            return {"success": False, "error": "Failed to cancel event"}

    def search_calendar_events(self,
                             agent_id: str,
                             start_date: str,  # ISO date format
                             end_date: str,    # ISO date format
                             query: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for events in the agent's calendar

        Args:
            agent_id: The agent's ID
            start_date: Start date in ISO format (e.g., "2024-01-15")
            end_date: End date in ISO format (e.g., "2024-01-20")
            query: Search query for event content (optional)

        Returns:
            Dict with success status and list of matching events
        """
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Parse dates
            start_dt = datetime.fromisoformat(start_date).replace(hour=0, minute=0, second=0)
            end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)

            events = self.calendar_service.search_events(agent, start_dt, end_dt, query)

            # Format events for AI consumption
            formatted_events = []
            for event in events:
                if event.get('status') == 'cancelled':
                    continue

                # Extract client info from extended properties
                extended_props = event.get('extendedProperties', {}).get('private', {})

                formatted_events.append({
                    "id": event['id'],
                    "summary": event.get('summary', 'No title'),
                    "start": event['start'].get('dateTime', event['start'].get('date')),
                    "end": event['end'].get('dateTime', event['end'].get('date')),
                    "description": event.get('description', ''),
                    "location": event.get('location', ''),
                    "attendees": [a.get('email') for a in event.get('attendees', [])],
                    "client_name": extended_props.get('client_name', ''),
                    "client_phone": extended_props.get('client_phone', ''),
                    "status": event.get('status', 'confirmed')
                })

            return {
                "success": True,
                "events": formatted_events,
                "total_found": len(formatted_events)
            }

        except Exception as e:
            app_logger.error(f"Error searching events for agent {agent_id}: {str(e)}")
            return {"success": False, "error": "Failed to search events"}

    def update_calendar_event(self,
                            agent_id: str,
                            event_id: str,
                            summary: Optional[str] = None,
                            start_datetime: Optional[str] = None,
                            duration_minutes: Optional[int] = None,
                            description: Optional[str] = None,
                            location: Optional[str] = None,
                            attendees: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Update an existing calendar event

        Args:
            agent_id: The agent's ID
            event_id: The Google Calendar event ID
            summary: New event title/summary
            start_datetime: New start time in ISO format
            duration_minutes: New duration in minutes
            description: New description
            location: New location
            attendees: New list of attendee emails

        Returns:
            Dict with success status and updated event details
        """
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            if not agent.booking_enabled:
                return {"success": False, "error": "Calendar booking is disabled for this agent"}

            # Build update dictionary
            updates = {}

            if summary is not None:
                updates['summary'] = summary

            if description is not None:
                updates['description'] = description

            if location is not None:
                updates['location'] = location

            if attendees is not None:
                # Merge default invitees with specific attendees when updating
                all_attendees = []

                # Add default invitees from agent settings
                if agent.invitees:
                    for invitee in agent.invitees:
                        if invitee.get("email"):
                            all_attendees.append(invitee["email"])

                # Add specific attendees for this event
                all_attendees.extend(attendees)

                # Remove duplicates while preserving order
                unique_attendees = []
                seen = set()
                for email in all_attendees:
                    if email not in seen:
                        unique_attendees.append(email)
                        seen.add(email)

                updates['attendees'] = [{'email': email} for email in unique_attendees]

            # Handle time updates
            if start_datetime is not None:
                start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                updates['start'] = {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': 'UTC'
                }

                # Calculate end time
                if duration_minutes is not None:
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                else:
                    # Get current event to preserve duration
                    current_event = self.calendar_service.service.events().get(
                        calendarId=agent.calendar_id,
                        eventId=event_id
                    ).execute()

                    current_start = datetime.fromisoformat(current_event['start']['dateTime'].replace('Z', '+00:00'))
                    current_end = datetime.fromisoformat(current_event['end']['dateTime'].replace('Z', '+00:00'))
                    current_duration = (current_end - current_start).total_seconds() / 60
                    end_dt = start_dt + timedelta(minutes=current_duration)

                updates['end'] = {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': 'UTC'
                }

            updated_event = self.calendar_service.update_event(agent, event_id, updates)

            app_logger.info(f"Updated event {event_id} for agent {agent_id}")

            return {
                "success": True,
                "event_id": updated_event['id'],
                "summary": updated_event['summary'],
                "start": updated_event['start']['dateTime'],
                "end": updated_event['end']['dateTime'],
                "location": updated_event.get('location'),
                "attendees": [a.get('email') for a in updated_event.get('attendees', [])]
            }

        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            app_logger.error(f"Error updating event {event_id}: {str(e)}")
            return {"success": False, "error": "Failed to update event"}

    def list_calendar_events(self,
                           agent_id: str,
                           start_date: str,  # ISO date format
                           end_date: str,    # ISO date format
                           include_cancelled: bool = False) -> Dict[str, Any]:
        """
        List all events for a given date range

        Args:
            agent_id: The agent's ID
            start_date: Start date in ISO format (e.g., "2024-01-15")
            end_date: End date in ISO format (e.g., "2024-01-20")
            include_cancelled: Whether to include cancelled events

        Returns:
            Dict with success status and list of events
        """
        try:
            agent = self.db_session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Parse dates
            start_dt = datetime.fromisoformat(start_date).replace(hour=0, minute=0, second=0)
            end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)

            events = self.calendar_service.list_events(agent, start_dt, end_dt, include_cancelled)

            # Format events for AI consumption
            formatted_events = []
            for event in events:
                # Extract client info from extended properties
                extended_props = event.get('extendedProperties', {}).get('private', {})

                formatted_events.append({
                    "id": event['id'],
                    "summary": event.get('summary', 'No title'),
                    "start": event['start'].get('dateTime', event['start'].get('date')),
                    "end": event['end'].get('dateTime', event['end'].get('date')),
                    "description": event.get('description', ''),
                    "location": event.get('location', ''),
                    "attendees": [a.get('email') for a in event.get('attendees', [])],
                    "client_name": extended_props.get('client_name', ''),
                    "client_phone": extended_props.get('client_phone', ''),
                    "status": event.get('status', 'confirmed')
                })

            # Also get available slots for the period
            all_available_slots = []
            current_date = start_dt.date()
            while current_date <= end_dt.date():
                day_start = datetime.combine(current_date, datetime.min.time())
                day_end = datetime.combine(current_date, datetime.max.time())

                daily_slots = self.calendar_service.get_available_slots(
                    agent, day_start, day_end, agent.default_slot_duration
                )
                all_available_slots.extend(daily_slots)
                current_date += timedelta(days=1)

            return {
                "success": True,
                "events": formatted_events,
                "total_events": len(formatted_events),
                "available_slots": all_available_slots[:20],  # Limit to first 20 slots
                "date_range": {
                    "start": start_date,
                    "end": end_date
                }
            }

        except Exception as e:
            app_logger.error(f"Error listing events for agent {agent_id}: {str(e)}")
            return {"success": False, "error": "Failed to list events"}


# Function definitions for agent tool registry
def create_calendar_event_function():
    """Function definition for create_calendar_event tool"""
    return {
        "name": "create_calendar_event",
        "description": "Create a calendar event/booking for the agent. Always check available slots first before booking.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent's ID"
                },
                "summary": {
                    "type": "string",
                    "description": "Event title/summary"
                },
                "start_datetime": {
                    "type": "string",
                    "description": "Start time in ISO format (e.g., '2024-01-15T14:00:00')"
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Event duration in minutes",
                    "default": 30
                },
                "client_name": {
                    "type": "string",
                    "description": "Client's name (optional)"
                },
                "client_phone": {
                    "type": "string",
                    "description": "Client's phone number (include if provided)"
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses"
                },
                "description": {
                    "type": "string",
                    "description": "Event description"
                },
                "location": {
                    "type": "string",
                    "description": "Event location"
                }
            },
            "required": ["agent_id", "summary", "start_datetime"]
        }
    }

def cancel_calendar_event_function():
    """Function definition for cancel_calendar_event tool"""
    return {
        "name": "cancel_calendar_event",
        "description": "Cancel/remove a calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent's ID"
                },
                "event_id": {
                    "type": "string",
                    "description": "The Google Calendar event ID"
                }
            },
            "required": ["agent_id", "event_id"]
        }
    }

def search_calendar_events_function():
    """Function definition for search_calendar_events tool"""
    return {
        "name": "search_calendar_events",
        "description": "Search for events in the agent's calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent's ID"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in ISO format (e.g., '2024-01-15')"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in ISO format (e.g., '2024-01-20')"
                },
                "query": {
                    "type": "string",
                    "description": "Search query for event content (optional)"
                }
            },
            "required": ["agent_id", "start_date", "end_date"]
        }
    }

def update_calendar_event_function():
    """Function definition for update_calendar_event tool"""
    return {
        "name": "update_calendar_event",
        "description": "Update an existing calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent's ID"
                },
                "event_id": {
                    "type": "string",
                    "description": "The Google Calendar event ID"
                },
                "summary": {
                    "type": "string",
                    "description": "New event title/summary"
                },
                "start_datetime": {
                    "type": "string",
                    "description": "New start time in ISO format"
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "New duration in minutes"
                },
                "description": {
                    "type": "string",
                    "description": "New description"
                },
                "location": {
                    "type": "string",
                    "description": "New location"
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New list of attendee emails"
                }
            },
            "required": ["agent_id", "event_id"]
        }
    }

def list_calendar_events_function():
    """Function definition for list_calendar_events tool"""
    return {
        "name": "list_calendar_events",
        "description": "List all events and available slots for a given date range",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent's ID"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in ISO format (e.g., '2024-01-15')"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in ISO format (e.g., '2024-01-20')"
                },
                "include_cancelled": {
                    "type": "boolean",
                    "description": "Whether to include cancelled events",
                    "default": False
                }
            },
            "required": ["agent_id", "start_date", "end_date"]
        }
    }