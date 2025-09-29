from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.agent_schemas import AgentCreateRequest, AgentResponse
from app.models import get_db, Agent, User, AgentUser
from app.services.calendar_service import CalendarService, CalendarCreateRequest

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
        agent_data: AgentCreateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Create a new agent, create a calendar, and assign the current user as owner."""
    agent = Agent(**agent_data.model_dump())
    db.add(agent)
    db.flush()  # Flush to get the agent ID

    # Create Google Calendar for agent
    calendar_service = CalendarService()
    calendar_req = CalendarCreateRequest(
        summary=agent_data.business_name,
        timeZone=agent_data.timezone if hasattr(agent_data, "timezone") else "UTC"
    )
    try:
        calendar = calendar_service.create_calendar(calendar_req)
        agent.calendar_id = calendar["id"]
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Calendar creation failed: {str(e)}")

    # Assign current user as owner
    agent_user = AgentUser(agent_id=agent.id, user_id=current_user.id, role="owner")
    db.add(agent_user)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=List[AgentResponse])
def get_user_agents(
        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all agents associated with the current user."""
    return (
        db.query(Agent)
        .join(AgentUser)
        .filter(AgentUser.user_id == current_user.id, Agent.active)
        .all()
    )
