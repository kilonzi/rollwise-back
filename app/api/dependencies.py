
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.models import get_db, Agent
from app.services.user_service import UserService

security = HTTPBearer()

from pydantic import BaseModel


class UserPayload(BaseModel):
    id: str
    email: str
    firebase_uid: str
    email_verified: bool
    exp: int


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserPayload:
    """
    Verifies JWT token and returns the user payload as a Pydantic model.
    Raises HTTPException for invalid tokens.
    """
    token = credentials.credentials
    payload = UserService.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPayload(**payload)


def validate_agent_access(
        agent_id: str,
        current_user: UserPayload = Depends(get_current_user),
        db: Session = Depends(get_db)
) -> type[Agent]:
    """
    Validates that the current user has access to the requested agent.
    Returns the agent object if access is validated, otherwise raises HTTPException.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    if agent.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this agent",
        )

    return agent
