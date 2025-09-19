from pydantic import BaseModel
from typing import Optional


class TenantResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    business_type: Optional[str]
    role: str
    joined_at: str

    class Config:
        orm_mode = True


class UserTenantAssociation(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "user"

