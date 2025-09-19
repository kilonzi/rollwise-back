from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserRegistration(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone_number: Optional[str] = None
    tenant_id: Optional[str] = None
    role: str = "user"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    reset_token: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone_number: Optional[str]
    global_role: str
    active: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        orm_mode = True

