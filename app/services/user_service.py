from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models import User

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 5


class UserService:
    """Service for user management and authentication (firebase-based)"""

    @staticmethod
    def create_access_token(
        data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except Exception:
            return None

    @staticmethod
    def upsert_user(db: Session, user_data: Dict[str, Any]) -> User:
        """Create or update a user by firebase_uid/email."""
        user = (
            db.query(User)
            .filter(
                (User.firebase_uid == user_data["firebase_uid"])
                | (User.email == user_data["email"])
            )
            .first()
        )
        if user:
            user.email = user_data["email"]
            user.firebase_uid = user_data["firebase_uid"]
            user.email_verified = user_data["email_verified"]
            user.name = user_data.get("name")
            user.phone_number = user_data.get("phone_number")
            user.photo_url = user_data.get("photo_url")
            user.provider = user_data.get("provider")
            user.metadata = user_data.get("metadata")
            user.updated_at = datetime.utcnow()
        else:
            user = User(
                email=user_data["email"],
                firebase_uid=user_data["firebase_uid"],
                email_verified=user_data["email_verified"],
                name=user_data.get("name"),
                phone_number=user_data.get("phone_number"),
                photo_url=user_data.get("photo_url"),
                provider=user_data.get("provider"),
                user_metadata=user_data.get("metadata"),
            )
            db.add(user)
        db.commit()
        db.refresh(user)
        return user
