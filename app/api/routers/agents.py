from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.agent_schemas import (
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentResponse,
    AgentUserResponse,
    AgentUserInviteRequest,
    AgentUserAssignByIdRequest,
    AgentUserUnassignRequest,
)
from app.models import get_db, Agent, User, AgentUser
from app.utils.logging_config import app_logger

router = APIRouter()


@router.post("", response_model=AgentResponse)
async def create_agent(
        agent_data: AgentCreateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Create a new agent and assign the current user as owner"""
    try:
        agent = Agent(
            name=agent_data.name,
            greeting=agent_data.greeting,
            voice_model=agent_data.voice_model,
            eleven_labs_voice_id=agent_data.eleven_labs_voice_id,
            voice_provider=agent_data.voice_provider,
            system_prompt=agent_data.system_prompt,
            language=agent_data.language,
            tools=[],
            business_hours=agent_data.business_hours,
            default_slot_duration=30,
            max_slot_appointments=1,
            buffer_time=10,
            invitees=[{"email": current_user.email, "availability": "always"}],
            booking_enabled=True,
        )

        db.add(agent)
        db.flush()

        # Assign the current user as the owner of the new agent
        agent_user = AgentUser(agent_id=agent.id, user_id=current_user.id, role="owner")
        db.add(agent_user)

        try:
            from app.services.calendar_service import CalendarService

            calendar_service = CalendarService()
            calendar_id = calendar_service.create_agent_calendar(agent.id, agent.name)
            agent.calendar_id = calendar_id
            app_logger.info(f"Created calendar {calendar_id} for agent {agent.id}")
        except Exception as e:
            app_logger.error(f"Error creating calendar for agent {agent.id}: {str(e)}")

        db.commit()
        db.refresh(agent)

        return agent

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.get("", response_model=List[AgentResponse])
async def get_user_agents(
        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all agents associated with the current user"""
    agents = (
        db.query(Agent)
        .join(AgentUser)
        .filter(AgentUser.user_id == current_user.id, Agent.active)
        .all()
    )
    return agents


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_by_id(
        agent_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Get a specific agent by ID"""
    agent = (
        db.query(Agent)
        .join(AgentUser)
        .filter(
            Agent.id == agent_id,
            AgentUser.user_id == current_user.id,
            Agent.active,
        )
        .first()
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
        agent_id: str,
        agent_data: AgentUpdateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Update an agent if the user is an owner or editor"""
    agent_user = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role.in_(["owner", "editor"]),
        )
        .first()
    )
    if not agent_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this agent",
        )

    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    try:
        agent_dict = agent_data.model_dump(exclude_unset=True)
        for field, value in agent_dict.items():
            if value is not None:
                setattr(agent, field, value)

        agent.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(agent)

        return agent

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.delete("/{agent_id}")
async def delete_agent(
        agent_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Delete (deactivate) an agent if the user is an owner"""
    agent_user = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role == "owner",
        )
        .first()
    )
    if not agent_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can delete this agent",
        )

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    try:
        agent.active = False
        agent.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"message": "Agent deleted successfully", "agent_id": agent.id}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete agent: {str(e)}",
        )


@router.get("/{agent_id}/users", response_model=List[AgentUserResponse])
async def get_agent_users(
        agent_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Get all users and their roles for a specific agent"""
    # Verify that the current user has access to this agent
    requester_agent_user = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
        )
        .first()
    )
    if not requester_agent_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this agent's users",
        )

    # Get all user associations for the agent
    agent_users = db.query(AgentUser).filter(AgentUser.agent_id == agent_id).all()
    return agent_users


@router.post("/{agent_id}/users/invite", response_model=AgentUserResponse)
async def invite_user_to_agent(
        agent_id: str,
        invite_data: AgentUserInviteRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Invite a user to an agent by email and assign a role."""
    # Check if current user is owner or editor
    agent_user_permission = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role.in_(["owner", "editor"]),
        )
        .first()
    )
    if not agent_user_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to invite users to this agent",
        )

    user_to_invite = db.query(User).filter(User.email == invite_data.email).first()
    if not user_to_invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email {invite_data.email} not found",
        )

    existing_agent_user = (
        db.query(AgentUser)
        .filter(AgentUser.agent_id == agent_id, AgentUser.user_id == user_to_invite.id)
        .first()
    )
    if existing_agent_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this agent",
        )

    new_agent_user = AgentUser(
        agent_id=agent_id, user_id=user_to_invite.id, role=invite_data.role
    )
    db.add(new_agent_user)
    db.commit()
    db.refresh(new_agent_user)

    return new_agent_user


@router.post("/{agent_id}/users/assign_by_id", response_model=AgentUserResponse)
async def assign_user_by_id(
        agent_id: str,
        assign_data: AgentUserAssignByIdRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Assign a user to an agent by user ID and assign a role."""
    agent_user_permission = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role.in_(["owner", "editor"]),
        )
        .first()
    )
    if not agent_user_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to assign users to this agent",
        )

    user_to_assign = db.query(User).filter(User.id == assign_data.user_id).first()
    if not user_to_assign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {assign_data.user_id} not found",
        )

    existing_agent_user = (
        db.query(AgentUser)
        .filter(AgentUser.agent_id == agent_id, AgentUser.user_id == user_to_assign.id)
        .first()
    )
    if existing_agent_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this agent",
        )

    new_agent_user = AgentUser(
        agent_id=agent_id, user_id=user_to_assign.id, role=assign_data.role
    )
    db.add(new_agent_user)
    db.commit()
    db.refresh(new_agent_user)

    return new_agent_user


@router.post("/{agent_id}/users/unassign")
async def unassign_user_from_agent(
        agent_id: str,
        unassign_data: AgentUserUnassignRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Unassign a user from an agent."""
    agent_user_permission = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == current_user.id,
            AgentUser.role.in_(["owner", "editor"]),
        )
        .first()
    )
    if not agent_user_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to unassign users from this agent",
        )

    agent_user_to_unassign = (
        db.query(AgentUser)
        .filter(
            AgentUser.agent_id == agent_id,
            AgentUser.user_id == unassign_data.user_id,
        )
        .first()
    )

    if not agent_user_to_unassign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this agent",
        )

    # Prevent removing the last owner
    if agent_user_to_unassign.role == "owner":
        owner_count = (
            db.query(AgentUser)
            .filter(AgentUser.agent_id == agent_id, AgentUser.role == "owner")
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot unassign the last owner of the agent",
            )

    db.delete(agent_user_to_unassign)
    db.commit()

    return {"message": "User unassigned successfully"}
