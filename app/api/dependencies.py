from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.models import get_db, Agent, AgentUser
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
    db: Session = Depends(get_db),
) -> Agent:
    """
    Validates that the current user has access to the requested agent.
    Returns the agent object if access is validated, otherwise raises HTTPException.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Check if user has access to this agent through AgentUser relationship
    agent_user = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
        )
        .first()
    )

    if not agent_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this agent",
        )

    return agent


def validate_agent_access_with_role(
    agent_id: str,
    required_roles: list[str],
    current_user: UserPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[Agent, str]:
    """
    Validates that the current user has access to the requested agent with specific role(s).
    Returns tuple of (agent, user_role) if access is validated, otherwise raises HTTPException.

    Args:
        agent_id: The agent ID to validate access for
        required_roles: List of roles that are allowed (e.g., ["owner", "editor"])
        current_user: Current user payload from JWT
        db: Database session

    Returns:
        Tuple of (Agent, user_role_string)
    """
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Check if user has access to this agent with required role
    agent_user = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role.in_(required_roles),
        )
        .first()
    )

    if not agent_user:
        roles_str = ", ".join(required_roles)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have required permissions. Required roles: {roles_str}",
        )

    return agent, agent_user.role
