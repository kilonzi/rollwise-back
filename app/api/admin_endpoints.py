from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import get_db, Tenant, Agent, Conversation

router = APIRouter(prefix="/admin", tags=["admin"])


# Pydantic models for API
class TenantCreate(BaseModel):
    name: str
    business_type: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    business_type: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    active: Optional[bool] = None


class UserCreate(BaseModel):
    tenant_id: str
    name: str
    email: str
    phone_number: Optional[str] = None
    role: str = "user"


class AgentCreate(BaseModel):
    tenant_id: str
    name: str
    phone_number: str
    greeting: Optional[str] = "Hello! How can I help you today?"
    voice_model: str = "aura-2-thalia-en"
    system_prompt: Optional[str] = "You are a helpful AI assistant."
    language: str = "en"
    tools: List[str] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    greeting: Optional[str] = None
    voice_model: Optional[str] = None
    system_prompt: Optional[str] = None
    language: Optional[str] = None
    tools: Optional[List[str]] = None
    active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    business_type: Optional[str]
    active: bool
    created_at: str

    class Config:
        from_attributes = True


class AgentResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    phone_number: str
    greeting: str
    voice_model: str
    active: bool
    created_at: str

    class Config:
        from_attributes = True


# Tenant management endpoints
@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant"""
    db_tenant = Tenant(
        name=tenant.name,
        business_type=tenant.business_type,
        phone_number=tenant.phone_number,
        email=tenant.email,
        address=tenant.address,
    )

    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)

    return TenantResponse(
        id=db_tenant.id,
        name=db_tenant.name,
        business_type=db_tenant.business_type,
        active=db_tenant.active,
        created_at=db_tenant.created_at.isoformat(),
    )


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(include_inactive: bool = False, db: Session = Depends(get_db)):
    """List all tenants (active by default)"""
    query = db.query(Tenant)

    if not include_inactive:
        query = query.filter(Tenant.active)

    tenants = query.all()

    return [
        TenantResponse(
            id=t.id,
            name=t.name,
            business_type=t.business_type,
            active=t.active,
            created_at=t.created_at.isoformat(),
        )
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get a specific tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        business_type=tenant.business_type,
        active=tenant.active,
        created_at=tenant.created_at.isoformat(),
    )


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str, tenant_update: TenantUpdate, db: Session = Depends(get_db)
):
    """Update a tenant (including activation/deactivation)"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Update fields if provided
    if tenant_update.name is not None:
        tenant.name = tenant_update.name
    if tenant_update.business_type is not None:
        tenant.business_type = tenant_update.business_type
    if tenant_update.phone_number is not None:
        tenant.phone_number = tenant_update.phone_number
    if tenant_update.email is not None:
        tenant.email = tenant_update.email
    if tenant_update.address is not None:
        tenant.address = tenant_update.address
    if tenant_update.active is not None:
        tenant.active = tenant_update.active

    db.commit()
    db.refresh(tenant)

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        business_type=tenant.business_type,
        active=tenant.active,
        created_at=tenant.created_at.isoformat(),
    )


# Agent management endpoints
@router.post("/agents", response_model=AgentResponse)
async def create_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    """Create a new agent"""

    # Verify tenant exists and is active
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == agent.tenant_id, Tenant.active)
        .first()
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive")

    # Check if phone number is already in use
    existing_agent = (
        db.query(Agent)
        .filter(Agent.phone_number == agent.phone_number, Agent.active)
        .first()
    )

    if existing_agent:
        raise HTTPException(status_code=400, detail="Phone number already in use")

    db_agent = Agent(
        tenant_id=agent.tenant_id,
        name=agent.name,
        phone_number=agent.phone_number,
        greeting=agent.greeting,
        voice_model=agent.voice_model,
        system_prompt=agent.system_prompt,
        language=agent.language,
        tools=agent.tools,
    )

    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    return AgentResponse(
        id=db_agent.id,
        tenant_id=db_agent.tenant_id,
        name=db_agent.name,
        phone_number=db_agent.phone_number,
        greeting=db_agent.greeting,
        voice_model=db_agent.voice_model,
        active=db_agent.active,
        created_at=db_agent.created_at.isoformat(),
    )


@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    tenant_id: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """List all agents or agents for a specific tenant (active by default)"""
    query = db.query(Agent).join(Tenant)

    if tenant_id:
        query = query.filter(Agent.tenant_id == tenant_id)

    if not include_inactive:
        query = query.filter(Agent.active, Tenant.active)

    agents = query.all()

    return [
        AgentResponse(
            id=a.id,
            tenant_id=a.tenant_id,
            name=a.name,
            phone_number=a.phone_number,
            greeting=a.greeting,
            voice_model=a.voice_model,
            active=a.active,
            created_at=a.created_at.isoformat(),
        )
        for a in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """Get a specific agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentResponse(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        phone_number=agent.phone_number,
        greeting=agent.greeting,
        voice_model=agent.voice_model,
        active=agent.active,
        created_at=agent.created_at.isoformat(),
    )


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str, agent_update: AgentUpdate, db: Session = Depends(get_db)
):
    """Update an agent (including activation/deactivation)"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Update fields if provided
    if agent_update.name is not None:
        agent.name = agent_update.name
    if agent_update.greeting is not None:
        agent.greeting = agent_update.greeting
    if agent_update.voice_model is not None:
        agent.voice_model = agent_update.voice_model
    if agent_update.system_prompt is not None:
        agent.system_prompt = agent_update.system_prompt
    if agent_update.language is not None:
        agent.language = agent_update.language
    if agent_update.tools is not None:
        agent.tools = agent_update.tools
    if agent_update.active is not None:
        agent.active = agent_update.active

    db.commit()
    db.refresh(agent)

    return AgentResponse(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        phone_number=agent.phone_number,
        greeting=agent.greeting,
        voice_model=agent.voice_model,
        active=agent.active,
        created_at=agent.created_at.isoformat(),
    )


@router.get("/tenants/{tenant_id}/conversations")
async def get_tenant_conversations(
    tenant_id: str, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
):
    """Get conversations for a tenant"""

    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    conversations = (
        db.query(Conversation)
        .join(Agent)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.active,
            Agent.active,
        )
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        {
            "id": conv.id,
            "agent_id": conv.agent_id,
            "session_name": conv.session_name,
            "conversation_type": conv.conversation_type,
            "caller_phone": conv.caller_phone,
            "status": conv.status,
            "started_at": conv.started_at.isoformat(),
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
            "duration_seconds": conv.duration_seconds,
        }
        for conv in conversations
    ]


@router.get("/agents/{agent_id}/conversations")
async def get_agent_conversations(
    agent_id: str, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
):
    """Get conversations for an agent"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.agent_id == agent_id, Conversation.active)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        {
            "id": conv.id,
            "session_name": conv.session_name,
            "conversation_type": conv.conversation_type,
            "caller_phone": conv.caller_phone,
            "status": conv.status,
            "started_at": conv.started_at.isoformat(),
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
            "duration_seconds": conv.duration_seconds,
        }
        for conv in conversations
    ]


# Administrative endpoints for activation/deactivation
@router.post("/tenants/{tenant_id}/deactivate")
async def deactivate_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Deactivate a tenant (stops all their agents from working)"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.active = False
    db.commit()

    return {
        "message": f"Tenant '{tenant.name}' has been deactivated",
        "tenant_id": tenant_id,
        "active": False,
    }


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Activate a tenant (re-enables all their agents)"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.active = True
    db.commit()

    return {
        "message": f"Tenant '{tenant.name}' has been activated",
        "tenant_id": tenant_id,
        "active": True,
    }


@router.post("/agents/{agent_id}/deactivate")
async def deactivate_agent(agent_id: str, db: Session = Depends(get_db)):
    """Deactivate a specific agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.active = False
    db.commit()

    return {
        "message": f"Agent '{agent.name}' has been deactivated",
        "agent_id": agent_id,
        "active": False,
    }


@router.post("/agents/{agent_id}/activate")
async def activate_agent(agent_id: str, db: Session = Depends(get_db)):
    """Activate a specific agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if tenant is also active
    if not agent.tenant.active:
        raise HTTPException(
            status_code=400, detail="Cannot activate agent: tenant is inactive"
        )

    agent.active = True
    db.commit()

    return {
        "message": f"Agent '{agent.name}' has been activated",
        "agent_id": agent_id,
        "active": True,
    }
