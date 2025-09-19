from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import get_db, Agent, Tenant, UserTenant
from app.services.agent_service import AgentService
from app.api.schemas.agent_schemas import AgentCreateRequest, AgentUpdateRequest, AgentResponse, PhoneNumberAssignment
from app.api.dependencies import get_current_user
from app.utils.logging_config import app_logger

router = APIRouter()


@router.post("/tenants/{tenant_id}/agents", response_model=AgentResponse)
async def create_tenant_agent(
    tenant_id: str,
    agent_data: AgentCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new agent for a tenant"""
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active
    ).first()

    if not user_tenant:
        if current_user["global_role"] != "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant"
            )
    elif user_tenant.role not in ["owner", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create agents"
        )

    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.active
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    try:
        user_email = current_user.get("email", "")
        user_name = current_user.get("name", "User")

        default_business_hours = {
            "start": "08:00",
            "end": "17:00",
            "timezone": "UTC",
            "days": [1, 2, 3, 4, 5]
        }

        default_invitees = [
            {
                "name": user_name,
                "email": user_email,
                "availability": "always"
            }
        ] if user_email else []

        agent = Agent(
            tenant_id=tenant_id,
            name=agent_data.name,
            greeting=agent_data.greeting,
            voice_model=agent_data.voice_model,
            eleven_labs_voice_id=agent_data.eleven_labs_voice_id,
            voice_provider=agent_data.voice_provider,
            system_prompt=agent_data.system_prompt,
            language=agent_data.language,
            tools=[],
            business_hours=default_business_hours,
            default_slot_duration=30,
            max_slot_appointments=1,
            buffer_time=10,
            invitees=default_invitees,
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


@router.put("/tenants/{tenant_id}/agents/{agent_id}", response_model=AgentResponse)
async def update_tenant_agent(
    tenant_id: str,
    agent_id: str,
    agent_data: AgentUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an agent"""
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active
    ).first()

    if not user_tenant:
        if current_user["global_role"] != "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant"
            )
    elif user_tenant.role not in ["owner", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update agents"
        )

    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
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


@router.delete("/tenants/{tenant_id}/agents/{agent_id}")
async def delete_tenant_agent(
    tenant_id: str,
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete (deactivate) an agent"""
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active
    ).first()

    if not user_tenant:
        if current_user["global_role"] != "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant"
            )
    elif user_tenant.role not in ["owner", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete agents"
        )

    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id
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


@router.put("/tenants/{tenant_id}/agents/{agent_id}/phone")
async def assign_agent_phone_number(
    tenant_id: str,
    agent_id: str,
    phone_data: PhoneNumberAssignment,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a phone number to an agent"""
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active
    ).first()

    if not user_tenant:
        if current_user["global_role"] != "platform_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant"
            )
    elif user_tenant.role not in ["owner", "platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to modify agents"
        )

    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.active
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    result = AgentService.assign_phone_number(db, agent_id, phone_data.phone_number)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return {
        "message": result["message"],
        "agent_id": result["agent_id"],
        "phone_number": result["phone_number"]
    }


@router.get("/tenants/{tenant_id}/agents-without-phone")
async def get_agents_without_phone_numbers(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all agents in a tenant that don't have phone numbers assigned"""
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active
    ).first()

    if not user_tenant and current_user["global_role"] != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant"
        )

    agents = AgentService.get_agents_without_phone(db, tenant_id)

    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "language": agent.language,
                "voice_model": agent.voice_model,
                "eleven_labs_voice_id": agent.eleven_labs_voice_id,
                "voice_provider": agent.voice_provider,
                "created_at": agent.created_at.isoformat()
            }
            for agent in agents
        ],
        "count": len(agents)
    }
