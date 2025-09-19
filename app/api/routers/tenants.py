from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.models import get_db, UserTenant, Agent
from app.services.user_service import UserService
from app.api.schemas.tenant_schemas import UserTenantAssociation
from app.api.schemas.agent_schemas import AgentResponse
from app.api.dependencies import get_current_user, require_role

router = APIRouter()


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

    agents = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.active
    ).all()

    return agents

