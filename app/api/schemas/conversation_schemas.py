from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ConversationResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    session_name: str
    conversation_type: str
    caller_phone: str
    twilio_sid: Optional[str]
    status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[str]
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    audio_file_path: Optional[str]
    sequence_number: int
    message_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
