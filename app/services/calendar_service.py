from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events"
]
SERVICE_ACCOUNT_FILE = "./credentials.json"
DELEGATED_USER = "booking@rollwise.app"

class CalendarCreateRequest(BaseModel):
    summary: str
    timeZone: str

class CalendarUpdateRequest(BaseModel):
    summary: Optional[str] = None
    timeZone: Optional[str] = None

class EventCreateRequest(BaseModel):
    summary: str
    start: Dict[str, Any]
    end: Dict[str, Any]
    description: Optional[str] = None
    phone_number: Optional[str] = None
    attendees: Optional[List[EmailStr]] = None

class EventUpdateRequest(BaseModel):
    summary: Optional[str] = None
    start: Optional[Dict[str, Any]] = None
    end: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    phone_number: Optional[str] = None
    attendees: Optional[List[EmailStr]] = None

class CalendarService:
    def __init__(self, delegated_user: str = DELEGATED_USER):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        delegated_creds = credentials.with_subject(delegated_user)
        self.service = build("calendar", "v3", credentials=delegated_creds)

    def create_calendar(self, req: CalendarCreateRequest) -> Dict[str, Any]:
        calendar = req.dict()
        return self.service.calendars().insert(body=calendar).execute()

    def get_calendar(self, calendar_id: str) -> Dict[str, Any]:
        return self.service.calendars().get(calendarId=calendar_id).execute()

    def update_calendar(self, calendar_id: str, req: CalendarUpdateRequest) -> Dict[str, Any]:
        update_fields = {k: v for k, v in req.dict().items() if v is not None}
        return self.service.calendars().update(calendarId=calendar_id, body=update_fields).execute()

    def delete_calendar(self, calendar_id: str) -> None:
        self.service.calendars().delete(calendarId=calendar_id).execute()

    def add_owner(self, calendar_id: str, email: EmailStr) -> Dict[str, Any]:
        rule = {
            "scope": {"type": "user", "value": email},
            "role": "owner"
        }
        return self.service.acl().insert(calendarId=calendar_id, body=rule).execute()

    def remove_owner(self, calendar_id: str, email: EmailStr) -> None:
        rule_id = f"user:{email}"
        self.service.acl().delete(calendarId=calendar_id, ruleId=rule_id).execute()

    def create_event(self, calendar_id: str, req: EventCreateRequest) -> Dict[str, Any]:
        event = req.dict(exclude_unset=True)
        if req.attendees:
            event["attendees"] = [{"email": e} for e in req.attendees]
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def get_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
        return self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    def update_event(self, calendar_id: str, event_id: str, req: EventUpdateRequest) -> Dict[str, Any]:
        update_fields = {k: v for k, v in req.dict().items() if v is not None}
        if req.attendees:
            update_fields["attendees"] = [{"email": e} for e in req.attendees]
        return self.service.events().update(calendarId=calendar_id, eventId=event_id, body=update_fields).execute()

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
