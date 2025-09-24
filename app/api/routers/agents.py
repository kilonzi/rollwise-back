from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.agent_schemas import AgentCreateRequest, AgentResponse
from app.models import get_db, Agent, User, AgentUser

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
        agent_data: AgentCreateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Create a new agent and assign the current user as owner."""
    agent = Agent(**agent_data.model_dump())
    db.add(agent)
    db.flush()  # Flush to get the agent ID

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
