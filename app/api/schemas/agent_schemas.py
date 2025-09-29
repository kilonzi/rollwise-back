from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

from .user_schemas import UserResponse


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
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
    ordering_enabled: Optional[bool] = None
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
    business_name: str
    phone_number: Optional[str] = None
    greeting: Optional[str] = None
    voice_model: Optional[str] = None
    eleven_labs_voice_id: Optional[str] = None
    voice_provider: Optional[str] = None
    system_prompt: Optional[str] = None
    language: Optional[str] = None
    tools: Optional[List[str]] = None
    timezone: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = None
    after_hours_behavior: Optional[str] = None
    after_hours_message: Optional[str] = None
    transfer_settings: Optional[Dict[str, Any]] = None
    default_slot_duration: Optional[int] = None
    max_slot_appointments: Optional[int] = None
    buffer_time: Optional[int] = None
    blocked_dates: Optional[List[str]] = None
    invitees: Optional[List[Dict[str, Any]]] = None
    booking_enabled: Optional[bool] = None
    closed: Optional[bool] = None
    closed_message: Optional[str] = None


class AgentUserResponse(BaseModel):
    role: str
    user: UserResponse

    class Config:
        from_attributes = True


class AgentUserInviteRequest(BaseModel):
    email: EmailStr
    role: str  # owner, editor, viewer


class AgentUserAssignByIdRequest(BaseModel):
    user_id: str
    role: str  # owner, editor, viewer


class AgentUserUnassignRequest(BaseModel):
    user_id: str


class AgentResponse(BaseModel):
    id: str
    name: str
    business_name: str
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
    transfer_settings: Optional[Dict[str, Any]] = None
    default_slot_duration: Optional[int] = None
    max_slot_appointments: Optional[int] = None
    buffer_time: Optional[int] = None
    blocked_dates: Optional[List[str]] = None
    invitees: Optional[List[Dict[str, Any]]] = None
    booking_enabled: Optional[bool] = None
    ordering_enabled: Optional[bool] = None
    closed: Optional[bool] = None
    closed_message: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    user_associations: List[AgentUserResponse] = []

    class Config:
        from_attributes = True


class PhoneNumberAssignment(BaseModel):
    phone_number: str


class AgentChatQuery(BaseModel):
    query: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
