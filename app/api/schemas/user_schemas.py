from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime


class UserUpsertRequest(BaseModel):
    email: EmailStr
    firebase_uid: str
    email_verified: bool
    name: Optional[str] = None
    phone_number: Optional[str] = None
    photo_url: Optional[str] = None
    provider: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    firebase_uid: str
    email_verified: bool
    name: Optional[str] = None
    phone_number: Optional[str] = None
    photo_url: Optional[str] = None
    provider: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="user_metadata")
    global_role: str
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
