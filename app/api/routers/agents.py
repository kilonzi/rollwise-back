from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.agent_schemas import AgentCreateRequest, AgentUpdateRequest, AgentResponse, PhoneNumberAssignment
from app.models import get_db, Agent, User
from app.services.agent_service import AgentService
from app.utils.logging_config import app_logger

router = APIRouter()


@router.post("/", response_model=AgentResponse)
async def create_agent(
        agent_data: AgentCreateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Create a new agent for the current user"""
    try:
        agent = Agent(
            user_id=current_user.id,
            name=agent_data.name,
            greeting=agent_data.greeting,
            voice_model=agent_data.voice_model,
            eleven_labs_voice_id=agent_data.eleven_labs_voice_id,
            voice_provider=agent_data.voice_provider,
            system_prompt=agent_data.system_prompt,
            language=agent_data.language,
            tools=[],
            business_hours={
                "start": "08:00", "end": "17:00", "timezone": "UTC", "days": [1, 2, 3, 4, 5]
            },
            default_slot_duration=30,
            max_slot_appointments=1,
            buffer_time=10,
            invitees=[{"email": current_user.email, "availability": "always"}],
            booking_enabled=True
        )

        db.add(agent)
        db.flush()

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
            detail=f"Failed to create agent: {str(e)}"
        )


@router.get("/", response_model=List[AgentResponse])
async def get_user_agents(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get all agents for the current user"""
    agents = db.query(Agent).filter(Agent.user_id == current_user.id, Agent.active).all()
    return agents


@router.get("/{agent_id}", response_model=List[AgentResponse])
async def get_user_agents(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get all agents for the current user"""
    agents = db.query(Agent).filter(Agent.user_id == current_user.id, Agent.active).all()
    return agents


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
        agent_id: str,
        agent_data: AgentUpdateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Update an agent"""
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id,
        Agent.active
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
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
            detail=f"Failed to update agent: {str(e)}"
        )


@router.delete("/{agent_id}")
async def delete_agent(
        agent_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Delete (deactivate) an agent"""
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    try:
        agent.active = False
        agent.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "message": "Agent deleted successfully",
            "agent_id": agent.id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete agent: {str(e)}"
        )
