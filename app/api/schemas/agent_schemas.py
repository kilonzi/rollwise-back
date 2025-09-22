from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    greeting: Optional[str] = None
    system_prompt: Optional[str] = None
    voice_model: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    voice_provider: Optional[str] = None
    language: Optional[str] = None
    tools: Optional[List[str]] = None
    calendar_id: Optional[str] = None
    timezone: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = None
    after_hours_behavior: Optional[str] = None
    after_hours_message: Optional[str] = None
    default_slot_duration: Optional[int] = None
    max_slot_appointments: Optional[int] = None
    buffer_time: Optional[int] = None
    blocked_dates: Optional[List[str]] = None
    invitees: Optional[List[Dict[str, Any]]] = None
    booking_enabled: Optional[bool] = None
    closed: Optional[bool] = None
    closed_message: Optional[str] = None
    transfer_settings: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None
    conversation_starters: Optional[List[str]] = None
    max_duration: Optional[int] = None

    class Config:
        extra = "forbid"


class AgentCreateRequest(BaseModel):
    name: str
    greeting: str
    system_prompt: str
    voice_model: str = "aura-2-thalia-en"
    eleven_labs_voice_id: Optional[str] = None
    voice_provider: str = "eleven_labs"
    conversation_starters: Optional[List[str]] = []
    max_duration: Optional[int] = 300
    language: str = "en"
    timezone: str = "America/New_York"
    business_hours: Optional[Dict[str, Any]] = {
        "mon": {"enabled": True, "open": "09:00", "close": "17:00"},
        "tue": {"enabled": True, "open": "09:00", "close": "17:00"},
        "wed": {"enabled": True, "open": "09:00", "close": "17:00"},
        "thu": {"enabled": True, "open": "09:00", "close": "17:00"},
        "fri": {"enabled": True, "open": "09:00", "close": "17:00"},
        "sat": {"enabled": False, "open": "", "close": ""},
        "sun": {"enabled": False, "open": "", "close": ""},
    }
    after_hours_behavior: str = "voicemail"
    after_hours_message: str = ""
    closed: bool = False
    closed_message: Optional[str] = None
    transfer_settings: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    phone_number: Optional[str]
    greeting: str
    system_prompt: str
    voice_model: str
    eleven_labs_voice_id: Optional[str] = None
    voice_provider: str
    language: str
    tools: Optional[List[str]] = None
    calendar_id: Optional[str] = None
    timezone: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = None
    after_hours_behavior: Optional[str] = None
    after_hours_message: Optional[str] = None
    default_slot_duration: Optional[int] = None
    max_slot_appointments: Optional[int] = None
    buffer_time: Optional[int] = None
    blocked_dates: Optional[List[str]] = None
    invitees: Optional[List[Dict[str, Any]]] = None
    booking_enabled: Optional[bool] = None
    closed: Optional[bool] = None
    closed_message: Optional[str] = None
    transfer_settings: Optional[Dict[str, Any]] = None
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PhoneNumberAssignment(BaseModel):
    phone_number: str


class AgentChatQuery(BaseModel):
    query: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
