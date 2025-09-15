from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import os

from app.models import get_db, User, Tenant, Agent, UserTenant, Conversation, Message, BusinessDataset
from app.services.user_service import UserService
from app.services.agent_service import AgentService
from app.services.agent_chat_service import AgentChatService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.audio_service import AudioService
from app.services.business_dataset_service import BusinessDatasetService
from app.utils.date_utils import normalize_date_range

router = APIRouter()
security = HTTPBearer()


# Pydantic models for request/response
class UserRegistration(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone_number: Optional[str] = None
    tenant_id: Optional[str] = None
    role: str = "user"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    reset_token: str
    new_password: str


class UserTenantAssociation(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "user"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone_number: Optional[str]
    global_role: str
    active: bool
    created_at: datetime
    last_login: Optional[datetime]


class TenantResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    business_type: Optional[str]
    role: str
    joined_at: str


class AgentCreate(BaseModel):
    name: str
    greeting: str
    voice_model: str
    language: str
    system_prompt: str


class PhoneNumberAssignment(BaseModel):
    phone_number: str


class AgentChatQuery(BaseModel):
    query: str
    date_from: Optional[datetime] = None  # Default will be set to yesterday
    date_to: Optional[datetime] = None    # Default will be set to now


class AgentResponse(BaseModel):
    id: str
    name: str
    phone_number: Optional[str]
    voice_model: str
    language: str
    active: bool
    created_at: datetime


# Authentication dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current authenticated user from token"""
    token = credentials.credentials
    result = UserService.validate_token(db, token)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["error"],
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return result["user"]


# Role-based access control
def require_role(required_roles: List[str]):
    """Decorator to require specific roles"""
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["global_role"] not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegistration, db: Session = Depends(get_db)):
    """Register a new user"""
    result = UserService.register_user(
        db=db,
        name=user_data.name,
        email=user_data.email,
        password=user_data.password,
        phone_number=user_data.phone_number,
        tenant_id=user_data.tenant_id,
        role=user_data.role
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return {
        "message": result["message"],
        "user_id": result["user_id"],
        "email_verification_required": True
    }


@router.post("/login")
async def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return tokens"""
    result = UserService.login_user(db, login_data.email, login_data.password)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["error"]
        )
    
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
        "user": result["user"]
    }


@router.post("/validate-token")
async def validate_token(current_user: dict = Depends(get_current_user)):
    """Validate current token and return user info"""
    return {
        "valid": True,
        "user": current_user
    }


@router.post("/password-reset-request")
async def request_password_reset(
    reset_request: PasswordResetRequest, 
    db: Session = Depends(get_db)
):
    """Request password reset token"""
    result = UserService.request_password_reset(db, reset_request.email)
    
    return {
        "message": result["message"],
        "success": result["success"]
    }


@router.post("/password-reset")
async def reset_password(reset_data: PasswordReset, db: Session = Depends(get_db)):
    """Reset password using reset token"""
    result = UserService.reset_password(
        db, 
        reset_data.reset_token, 
        reset_data.new_password
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return {"message": result["message"]}


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile"""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.get("/tenants", response_model=List[TenantResponse])
async def get_user_tenants(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tenants associated with current user"""
    result = UserService.get_user_tenants(db, current_user["id"])
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["tenants"]


@router.post("/tenants/associate")
async def associate_user_with_tenant(
    association: UserTenantAssociation,
    current_user: dict = Depends(require_role(["platform_admin"])),
    db: Session = Depends(get_db)
):
    """Associate user with tenant (Platform Admin only)"""
    result = UserService.add_user_to_tenant(
        db,
        association.user_id,
        association.tenant_id,
        association.role
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return {"message": result["message"]}


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def remove_user_from_tenant(
    tenant_id: str,
    user_id: str,
    current_user: dict = Depends(require_role(["platform_admin"])),
    db: Session = Depends(get_db)
):
    """Remove user from tenant (Platform Admin only)"""
    result = UserService.remove_user_from_tenant(db, user_id, tenant_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return {"message": result["message"]}


@router.get("/tenants/{tenant_id}/users")
async def get_tenant_users(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all users in a tenant"""
    # Check if current user has access to this tenant
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
    ).first()
    
    if not user_tenant and current_user["global_role"] != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant"
        )
    
    result = UserService.get_tenant_users(db, tenant_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["users"]


@router.get("/tenants/{tenant_id}/agents", response_model=List[AgentResponse])
async def get_tenant_agents(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all agents for a tenant"""
    # Check if current user has access to this tenant
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
    ).first()
    print(user_tenant)
    if not user_tenant and current_user["global_role"] != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant"
        )
    
    agents = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.active == True
    ).all()
    
    return agents


@router.post("/tenants/{tenant_id}/agents")
async def create_tenant_agent(
    tenant_id: str,
    agent_data: AgentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new agent for a tenant"""
    # Check if current user has owner/admin role in this tenant
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
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

    # Check if tenant exists
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.active == True
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Create agent
    try:
        agent = Agent(
            tenant_id=tenant_id,
            name=agent_data.name,
            greeting=agent_data.greeting,
            voice_model=agent_data.voice_model,
            system_prompt=agent_data.system_prompt,
            language=agent_data.language,
            tools=[]  # Default empty tools list
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        return {
            "message": "Agent created successfully. Phone number will be assigned shortly.",
            "agent_id": agent.id,
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "phone_number": agent.phone_number,
                "voice_model": agent.voice_model,
                "language": agent.language,
                "greeting": agent.greeting,
                "system_prompt": agent.system_prompt,
                "created_at": agent.created_at.isoformat()
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.put("/tenants/{tenant_id}/agents/{agent_id}")
async def update_tenant_agent(
    tenant_id: str,
    agent_id: str,
    agent_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an agent"""
    # Check permissions similar to create_tenant_agent
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
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
    
    # Find agent
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.active == True
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Update agent fields
    try:
        for field, value in agent_data.items():
            if hasattr(agent, field) and field not in ['id', 'tenant_id', 'created_at']:
                setattr(agent, field, value)
        
        agent.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "message": "Agent updated successfully",
            "agent_id": agent.id
        }
        
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
    # Check permissions similar to other agent operations
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
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
    
    # Find agent
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Deactivate agent
    try:
        agent.active = False
        agent.updated_at = datetime.utcnow()
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
    """Assign a phone number to an agent (for async phone number assignment)"""
    # Check permissions similar to other agent operations
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
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

    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.active == True
    ).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    # Assign phone number
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
    # Check tenant access
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
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
                "created_at": agent.created_at.isoformat()
            }
            for agent in agents
        ],
        "count": len(agents)
    }


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent_knowledge(
    agent_id: str,
    chat_query: AgentChatQuery,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat with agent's knowledge base and conversation history"""

    # Get agent and verify access
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.active == True
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    # Check if current user has access to this agent's tenant
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()

    if not user_tenant and current_user["global_role"] != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this agent's data"
        )

    # Initialize chat service and process query
    chat_service = AgentChatService(db)

    result = chat_service.query_agent_knowledge(
        agent_id=agent_id,
        query=chat_query.query,
        date_from=chat_query.date_from,
        date_to=chat_query.date_to
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "query": chat_query.query,
        "response": result["response"],
        "context_summary": result["context_summary"],
        "knowledge_matches": result["knowledge_matches"],
        "timestamp": datetime.now().isoformat()
    }

# -------- Conversations & Messages (with audio) --------


def _serialize_conversation(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "tenant_id": conv.tenant_id,
        "agent_id": conv.agent_id,
        "session_name": conv.session_name,
        "conversation_type": conv.conversation_type,
        "caller_phone": conv.caller_phone,
        "twilio_sid": conv.twilio_sid,
        "status": conv.status,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
        "duration_seconds": conv.duration_seconds,
        "summary": conv.summary,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def _serialize_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "content": msg.content,
        "audio_file_path": msg.audio_file_path,
        "sequence_number": msg.sequence_number,
        "message_type": msg.message_type,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
    }


@router.get("/tenants/{tenant_id}/conversations")
async def get_tenant_conversations(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List conversations for a tenant that the current user has access to."""
    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    service = ConversationService(db)
    conversations = service.get_tenant_conversations(tenant_id, limit=limit, offset=offset)
    return [_serialize_conversation(c) for c in conversations]


@router.get("/agents/{agent_id}/conversations")
async def get_agent_conversations(
    agent_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List conversations for a specific agent, ensuring user has access to the agent's tenant."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check via agent.tenant_id
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    service = ConversationService(db)
    conversations = service.get_agent_conversations(agent_id, limit=limit, offset=offset)
    return [_serialize_conversation(c) for c in conversations]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get messages for a conversation, including audio_file_path when available."""
    # Fetch conversation and check access
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.active == True).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == conversation.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    msg_service = MessageService(db)
    messages = msg_service.get_conversation_messages(conversation_id)
    return [_serialize_message(m) for m in messages]


@router.get("/messages/{message_id}/audio")
async def get_message_audio(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch and stream the audio file for a specific message. Ensures predictable path using message_id."""
    # Load message and parent conversation
    message = db.query(Message).filter(Message.id == message_id, Message.active == True).first()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    conversation = db.query(Conversation).filter(Conversation.id == message.conversation_id, Conversation.active == True).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == conversation.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    # Determine file path: prefer stored path; else rebuild predictable path and update message
    audio_path = message.audio_file_path
    if not audio_path:
        # Use predictable path: store/audio/{conversation_id}/{message_id}.wav
        audio_path = AudioService.get_audio_file_path(conversation.id, message.id)
        if os.path.exists(audio_path):
            # Persist the path for future calls
            msg_service = MessageService(db)
            msg_service.update_message_audio(message.id, audio_path)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found for this message")

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    filename = os.path.basename(audio_path)
    return FileResponse(path=audio_path, media_type="audio/wav", filename=filename)


@router.get("/conversations/{conversation_id}/messages/{message_id}/audio")
async def get_conversation_message_audio(
    conversation_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Alias endpoint to fetch audio for a message under a conversation path."""
    # Validate that the message belongs to the conversation
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.conversation_id == conversation_id,
        Message.active == True
    ).first()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found in conversation")
    audio_path = AudioService.get_audio_file_path(conversation_id, message_id)
    if not audio_path:
        audio_path = AudioService.get_audio_file_path(conversation_id, message_id)
        if os.path.exists(audio_path):
            msg_service = MessageService(db)
            msg_service.update_message_audio(message.id, audio_path)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found for this message")

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    filename = os.path.basename(audio_path)
    return FileResponse(path=audio_path, media_type="audio/wav", filename=filename)


# -------- Datasets CRUD under Agents --------

def _serialize_dataset(ds: BusinessDataset) -> dict:
    return {
        "id": ds.id,
        "tenant_id": ds.tenant_id,
        "agent_id": ds.agent_id,
        "label": ds.label,
        "file_name": ds.file_name,
        "file_path": ds.file_path,
        "file_type": ds.file_type,
        "columns": ds.columns or [],
        "record_count": ds.record_count,
        "uploaded_at": ds.uploaded_at.isoformat() if ds.uploaded_at else None,
        "processed_at": ds.processed_at.isoformat() if ds.processed_at else None,
        "active": ds.active,
        "extra_info": ds.extra_info or {},
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
    }


@router.get("/agents/{agent_id}/datasets")
async def list_agent_datasets(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all datasets for an agent (requires access to agent's tenant)."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    service = BusinessDatasetService(db)
    datasets = service.list_datasets(tenant_id=agent.tenant_id, agent_id=agent_id)
    return [_serialize_dataset(d) for d in datasets]


@router.post("/agents/{agent_id}/datasets")
async def create_agent_dataset(
    agent_id: str,
    label: str = Form(...),
    columns: Optional[str] = Form(None, description="Comma-separated list of important columns"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create and ingest a dataset for an agent. Accepts file upload and optional columns list."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    # Save uploaded file to predictable path
    try:
        base_dir = os.path.join("store", "datasets", agent_id)
        os.makedirs(base_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        safe_name = os.path.basename(file.filename or "uploaded")
        filename = f"{label}_{timestamp}_{safe_name}"
        file_path = os.path.join(base_dir, filename)
        contents = await file.read()
        with open(file_path, "wb") as out:
            out.write(contents)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to save file: {e}")

    # Determine file type from extension
    ext = os.path.splitext(file.filename or "")[1].lower().strip(".") or "csv"

    # Parse columns
    columns_list: List[str] = []
    if columns:
        columns_list = [c.strip() for c in columns.split(",") if c.strip()]

    try:
        service = BusinessDatasetService(db)
        dataset = service.upload_dataset(
            tenant_id=agent.tenant_id,
            agent_id=agent_id,
            label=label,
            file_path=file_path,
            file_name=filename,
            file_type=ext,
            extra_info={"uploaded_by": current_user["id"]},
            columns=columns_list
        )
        return {
            "message": "Dataset uploaded successfully",
            "dataset": _serialize_dataset(dataset)
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/agents/{agent_id}/datasets/{dataset_id}")
async def get_agent_dataset(
    agent_id: str,
    dataset_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single dataset for an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    service = BusinessDatasetService(db)
    dataset = service.get_dataset(dataset_id)
    if not dataset or dataset.agent_id != agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return _serialize_dataset(dataset)


@router.put("/agents/{agent_id}/datasets/{dataset_id}")
async def update_agent_dataset(
    agent_id: str,
    dataset_id: int,
    columns: Optional[List[str]] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a dataset's columns list (critical columns)."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    dataset = db.query(BusinessDataset).filter(
        BusinessDataset.id == dataset_id,
        BusinessDataset.agent_id == agent_id,
        BusinessDataset.active == True
    ).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    try:
        if columns is not None:
            dataset.columns = columns
            extra = dataset.extra_info or {}
            extra["columns"] = columns
            dataset.extra_info = extra
            dataset.updated_at = datetime.utcnow()
            db.commit()
        return {"message": "Dataset updated", "dataset": _serialize_dataset(dataset)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/agents/{agent_id}/datasets/{dataset_id}")
async def delete_agent_dataset(
    agent_id: str,
    dataset_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a dataset (soft delete and Chroma cleanup)."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Access check
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    service = BusinessDatasetService(db)
    # Ensure dataset belongs to agent before deletion
    dataset = service.get_dataset(dataset_id)
    if not dataset or dataset.agent_id != agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    success = service.delete_dataset(dataset_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete dataset")

    return {"message": "Dataset deleted", "dataset_id": dataset_id}


@router.get("/agents/{agent_id}/statistics")
async def get_agent_statistics(
    agent_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit_top_callers: int = 5,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get aggregated statistics for an agent within a date range.
    - Filters conversations by started_at in [date_from, date_to]
    - Computes counts, breakdowns, success rate, duration aggregates and buckets,
      and caller analytics (repeat callers, top callers).
    """
    # Validate agent and access
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == current_user["id"],
        UserTenant.tenant_id == agent.tenant_id,
        UserTenant.active == True
    ).first()
    if not user_tenant and current_user["global_role"].lower() != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this tenant")

    # Normalize date range for proper filtering
    # If no dates provided, defaults to last 7 days
    if date_from is None and date_to is None:
        from datetime import timedelta
        now = datetime.now()
        date_to = now
        date_from = now - timedelta(days=7)

    date_from, date_to = normalize_date_range(date_from, date_to)

    # Query conversations within range
    q = db.query(Conversation).filter(
        Conversation.agent_id == agent_id,
        Conversation.active == True,
        Conversation.started_at >= date_from,
        Conversation.started_at <= date_to,
    )
    conversations = q.all()

    total = len(conversations)

    def pct(x: int, d: int) -> float:
        return round((x / d) * 100.0, 2) if d > 0 else 0.0

    # Breakdown by type
    type_counts: dict[str, int] = {}
    for c in conversations:
        t = (c.conversation_type or "unknown").lower()
        type_counts[t] = type_counts.get(t, 0) + 1
    type_breakdown = {
        t: {"raw": cnt, "percentage": pct(cnt, total)} for t, cnt in sorted(type_counts.items())
    }

    # Breakdown by status
    status_counts: dict[str, int] = {}
    for c in conversations:
        s = (c.status or "unknown").lower()
        status_counts[s] = status_counts.get(s, 0) + 1
    status_breakdown = {
        s: {"raw": cnt, "percentage": pct(cnt, total)} for s, cnt in sorted(status_counts.items())
    }

    # Overall success rate (completed/total)
    completed = status_counts.get("completed", 0)
    success_rate = pct(completed, total)

    # Duration metrics (voice only)
    def compute_duration_seconds(c: Conversation) -> int:
        try:
            if c.duration_seconds:
                return int(c.duration_seconds)
            # fallback if ended_at exists
            if c.started_at and c.ended_at:
                return int((c.ended_at - c.started_at).total_seconds())
        except Exception:
            pass
        return 0

    voice_convs = [c for c in conversations if (c.conversation_type or "").lower() == "voice"]
    durations = [compute_duration_seconds(c) for c in voice_convs]
    total_call_duration = sum(durations)
    avg_call_duration = round(total_call_duration / len(durations), 2) if durations else 0.0

    # Duration buckets in minutes
    buckets = {
        "lt_1": 0,
        "1_2": 0,
        "2_5": 0,
        "5_10": 0,
        "10_plus": 0,
    }
    for sec in durations:
        mins = sec / 60.0
        if mins < 1:
            buckets["lt_1"] += 1
        elif mins < 2:
            buckets["1_2"] += 1
        elif mins < 5:
            buckets["2_5"] += 1
        elif mins < 10:
            buckets["5_10"] += 1
        else:
            buckets["10_plus"] += 1
    bucket_breakdown = {k: {"raw": v, "percentage": pct(v, len(durations) or 0)} for k, v in buckets.items()}

    # Caller analytics
    from collections import Counter
    phones = [c.caller_phone for c in conversations if c.caller_phone]
    phone_counts = Counter(phones)
    unique_callers = len(phone_counts)
    repeat_callers = {p: cnt for p, cnt in phone_counts.items() if cnt > 1}
    repeat_caller_count = len(repeat_callers)
    top_callers = [
        {"phone": p, "count": cnt}
        for p, cnt in phone_counts.most_common(max(1, limit_top_callers))
    ]

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "range": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "totals": {
            "conversations": total,
            "voice_conversations": len(voice_convs),
            "message_conversations": type_counts.get("message", 0),
        },
        "type_breakdown": type_breakdown,
        "status_breakdown": status_breakdown,
        "success_rate": success_rate,
        "durations": {
            "total_seconds": total_call_duration,
            "average_seconds": avg_call_duration,
            "bucket_breakdown": bucket_breakdown,
        },
        "callers": {
            "unique_callers": unique_callers,
            "repeat_caller_count": repeat_caller_count,
            "top_callers": top_callers,
        },
    }
