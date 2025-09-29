from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, validate_agent_access_with_role
from app.api.schemas.agent_schemas import (
    AgentResponse,
    AgentUpdateRequest,
    AgentUserAssignByIdRequest,
    AgentUserInviteRequest,
    AgentUserResponse,
    AgentUserUnassignRequest,
)
from app.models import Agent, AgentUser, User, get_db

router = APIRouter()


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent_by_id(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific agent by ID, if the user has access."""
    agent, _ = validate_agent_access_with_role(
        agent_id, ["owner", "editor", "viewer"], current_user, db
    )
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: str,
    agent_data: AgentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an agent's details if the user is an owner or editor."""
    agent, _ = validate_agent_access_with_role(
        agent_id, ["owner", "editor"], current_user, db
    )

    # Convert agent_data to dict and handle field mapping
    update_data = agent_data.model_dump(exclude_unset=True)

    # Map frontend field names to database field names
    if "enable_booking" in update_data:
        update_data["booking_enabled"] = update_data.pop("enable_booking")
    if "enable_order" in update_data:
        update_data["ordering_enabled"] = update_data.pop("enable_order")

    # Apply updates to the agent
    for key, value in update_data.items():
        setattr(agent, key, value)

    # Check if we need to create a calendar
    if (hasattr(agent, 'booking_enabled') and agent.booking_enabled and
        (not agent.calendar_id or agent.calendar_id is None)):

        from app.services.calendar_service import CalendarService, CalendarCreateRequest

        calendar_service = CalendarService()
        calendar_req = CalendarCreateRequest(
            summary=agent.business_name or agent.name,
            timeZone=agent.timezone if agent.timezone else "UTC"
        )
        try:
            calendar = calendar_service.create_calendar(calendar_req)
            agent.calendar_id = calendar["id"]
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Calendar creation failed: {str(e)}")

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate an agent if the user is an owner."""
    agent, _ = validate_agent_access_with_role(
        agent_id, ["owner"], current_user, db
    )
    agent.active = False
    db.commit()
    return None


@router.get("/{agent_id}/users", response_model=List[AgentUserResponse])
def get_agent_users(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all users associated with a specific agent."""
    validate_agent_access_with_role(
        agent_id, ["owner", "editor", "viewer"], current_user, db
    )
    return db.query(AgentUser).filter(AgentUser.agent_id == agent_id).all()


@router.post("/{agent_id}/users/invite", response_model=AgentUserResponse)
def invite_user_to_agent(
    agent_id: str,
    invite_data: AgentUserInviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invite a user to an agent by email."""
    validate_agent_access_with_role(agent_id, ["owner", "editor"], current_user, db)
    user_to_invite = db.query(User).filter(User.email == invite_data.email).first()
    if not user_to_invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    existing_assignment = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id, AgentUser.user_id == user_to_invite.id
        )
        .first()
    )
    if existing_assignment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already assigned to this agent",
        )
    new_assignment = AgentUser(
        agent_id=agent_id, user_id=user_to_invite.id, role=invite_data.role
    )
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)
    return new_assignment


@router.post("/{agent_id}/users/assign_by_id", response_model=AgentUserResponse)
def assign_user_by_id(
    agent_id: str,
    assign_data: AgentUserAssignByIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign a user to an agent by their user ID."""
    validate_agent_access_with_role(agent_id, ["owner", "editor"], current_user, db)
    user_to_assign = db.query(User).filter(User.id == assign_data.user_id).first()
    if not user_to_assign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    existing_assignment = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id, AgentUser.user_id == user_to_assign.id
        )
        .first()
    )
    if existing_assignment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already assigned to this agent",
        )
    new_assignment = AgentUser(
        agent_id=agent_id, user_id=user_to_assign.id, role=assign_data.role
    )
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)
    return new_assignment


@router.post("/{agent_id}/users/unassign", status_code=status.HTTP_204_NO_CONTENT)
def unassign_user_from_agent(
    agent_id: str,
    unassign_data: AgentUserUnassignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unassign a user from an agent."""
    validate_agent_access_with_role(agent_id, ["owner", "editor"], current_user, db)
    assignment_to_delete = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == unassign_data.user_id,
        )
        .first()
    )
    if not assignment_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User is not assigned to this agent"
        )
    if assignment_to_delete.role == "owner":
        owner_count = (
            db.query(AgentUser)
            .filter(AgentUser.agent_id == agent_id, AgentUser.role == "owner")
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner of the agent",
            )
    db.delete(assignment_to_delete)
    db.commit()
    return None
