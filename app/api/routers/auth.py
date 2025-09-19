from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models import get_db
from app.services.user_service import UserService
from app.api.schemas.user_schemas import UserRegistration, UserLogin, PasswordResetRequest, PasswordReset
from app.api.dependencies import get_current_user

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegistration, db: Session = Depends(get_db)):
    """Register a new user"""
    result = UserService.register_user(
        db=db,
        name=user_data.name,
        email=user_data.email,
        password=user_data.password,
        phone_number=user_data.phone_number,
        tenant_id=user_data.tenant_id,
        role=user_data.role
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return {
        "message": result["message"],
        "user_id": result["user_id"],
        "email_verification_required": True
    }


@router.post("/login")
async def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return tokens"""
    result = UserService.login_user(db, login_data.email, login_data.password)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["error"]
        )

    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
        "user": result["user"]
    }


@router.post("/validate-token")
async def validate_token(current_user: dict = Depends(get_current_user)):
    """Validate current token and return user info"""
    return {
        "valid": True,
        "user": current_user
    }


@router.post("/password-reset-request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset token"""
    result = UserService.request_password_reset(db, reset_request.email)

    return {
        "message": result["message"],
        "success": result["success"]
    }


@router.post("/password-reset")
async def reset_password(reset_data: PasswordReset, db: Session = Depends(get_db)):
    """Reset password using reset token"""
    result = UserService.reset_password(
        db,
        reset_data.reset_token,
        reset_data.new_password
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return {"message": result["message"]}

