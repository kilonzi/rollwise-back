from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.models import get_db, User
from app.services.user_service import UserService
from app.api.schemas.user_schemas import UserResponse
from app.api.schemas.tenant_schemas import TenantResponse
from app.api.dependencies import get_current_user

router = APIRouter()


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile"""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.get("/tenants", response_model=List[TenantResponse])
async def get_user_tenants(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tenants associated with current user"""
    result = UserService.get_user_tenants(db, current_user["id"])

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return result["tenants"]
