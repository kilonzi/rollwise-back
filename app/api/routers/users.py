from typing import Dict, Union

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.user_schemas import UserUpsertRequest, UserResponse
from app.models.database import get_db, User
from app.services.user_service import UserService

router = APIRouter()


@router.post("/login", response_model=Dict[str, Union[str, Dict, bool]], status_code=201)
def upsert_user(
        user_in: UserUpsertRequest,
        db: Session = Depends(get_db)
):
    """Create or update a user and return a JWT access token."""
    user = UserService.upsert_user(db, user_in.model_dump())
    data = {
        "id": user.id,
        "email": user.email,
        "firebase_uid": user.firebase_uid,
        "email_verified": user.email_verified,
    }
    access_token: str = UserService.create_access_token(data)
    data["access_token"] = access_token
    return data


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
