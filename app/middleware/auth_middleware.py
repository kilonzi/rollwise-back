from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from app.models import get_db_session, User, UserTenant
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
security = HTTPBearer()


class RoleBasedAccessControl:
    """Role-based access control middleware and utilities"""
    
    # Define role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {
        "user": 1,
        "owner": 2,
        "platform_admin": 3
    }
    
    # Define resource permissions
    RESOURCE_PERMISSIONS = {
        "tenant": {
            "read": ["user", "owner", "platform_admin"],
            "write": ["owner", "platform_admin"],
            "delete": ["platform_admin"]
        },
        "agent": {
            "read": ["user", "owner", "platform_admin"],
            "write": ["owner", "platform_admin"],
            "delete": ["owner", "platform_admin"]
        },
        "user": {
            "read": ["owner", "platform_admin"],
            "write": ["owner", "platform_admin"],
            "delete": ["platform_admin"]
        },
        "conversation": {
            "read": ["user", "owner", "platform_admin"],
            "write": ["user", "owner", "platform_admin"],
            "delete": ["owner", "platform_admin"]
        }
    }
    
    @staticmethod
    def get_user_from_token(token: str, db: Session) -> Optional[Dict[str, Any]]:
        """Extract user information from JWT token"""
        try:
            result = UserService.validate_token(db, token)
            if result["success"]:
                return result["user"]
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    @staticmethod
    def check_tenant_access(
        user_id: str, 
        tenant_id: str, 
        required_role: str,
        db: Session
    ) -> bool:
        """Check if user has required role in specific tenant"""
        try:
            # Platform admins have access to all tenants
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.global_role == "platform_admin":
                return True
            
            # Check tenant-specific role
            user_tenant = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == tenant_id,
                UserTenant.active
            ).first()
            
            if not user_tenant:
                return False
            
            user_role_level = RoleBasedAccessControl.ROLE_HIERARCHY.get(user_tenant.role, 0)
            required_role_level = RoleBasedAccessControl.ROLE_HIERARCHY.get(required_role, 999)
            
            return user_role_level >= required_role_level
            
        except Exception as e:
            logger.error(f"Tenant access check error: {e}")
            return False
    
    @staticmethod
    def check_resource_permission(
        user_role: str,
        resource_type: str,
        action: str
    ) -> bool:
        """Check if user role has permission for resource action"""
        try:
            resource_perms = RoleBasedAccessControl.RESOURCE_PERMISSIONS.get(resource_type, {})
            allowed_roles = resource_perms.get(action, [])
            return user_role in allowed_roles
        except Exception as e:
            logger.error(f"Resource permission check error: {e}")
            return False
    
    @staticmethod
    def get_user_tenant_role(user_id: str, tenant_id: str, db: Session) -> Optional[str]:
        """Get user's role in specific tenant"""
        try:
            user_tenant = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == tenant_id,
                UserTenant.active
            ).first()
            
            return user_tenant.role if user_tenant else None
            
        except Exception as e:
            logger.error(f"Get user tenant role error: {e}")
            return None
    
    @staticmethod
    def get_user_tenants_with_roles(user_id: str, db: Session) -> List[Dict[str, Any]]:
        """Get all tenants user has access to with their roles"""
        try:
            user_tenants = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.active
            ).all()
            
            tenants_with_roles = []
            for ut in user_tenants:
                tenants_with_roles.append({
                    "tenant_id": ut.tenant_id,
                    "role": ut.role,
                    "joined_at": ut.created_at
                })
            
            return tenants_with_roles
            
        except Exception as e:
            logger.error(f"Get user tenants with roles error: {e}")
            return []


class AuthMiddleware:
    """Authentication middleware for FastAPI"""
    
    def __init__(self):
        self.rbac = RoleBasedAccessControl()
    
    async def authenticate_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """Authenticate request and return user info"""
        try:
            # Check for Authorization header
            auth_header = request.headers.get("authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None
            
            # Extract token
            token = auth_header.split(" ")[1]
            
            # Validate token
            db = get_db_session()
            try:
                user = self.rbac.get_user_from_token(token, db)
                return user
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    def require_authentication(self):
        """Decorator to require authentication"""
        def decorator(func):
            async def wrapper(request: Request, *args, **kwargs):
                user = await self.authenticate_request(request)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                
                # Add user to request state
                request.state.user = user
                return await func(request, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def require_role(self, required_roles: List[str]):
        """Decorator to require specific global roles"""
        def decorator(func):
            async def wrapper(request: Request, *args, **kwargs):
                user = getattr(request.state, 'user', None)
                if not user:
                    user = await self.authenticate_request(request)
                    if not user:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required"
                        )
                    request.state.user = user
                
                if user["global_role"] not in required_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions"
                    )
                
                return await func(request, *args, **kwargs)
            
            return wrapper
        return decorator
    
    def require_tenant_access(self, tenant_id_param: str, required_role: str = "user"):
        """Decorator to require tenant access with specific role"""
        def decorator(func):
            async def wrapper(request: Request, *args, **kwargs):
                user = getattr(request.state, 'user', None)
                if not user:
                    user = await self.authenticate_request(request)
                    if not user:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required"
                        )
                    request.state.user = user
                
                # Get tenant_id from path parameters
                tenant_id = kwargs.get(tenant_id_param) or request.path_params.get(tenant_id_param)
                if not tenant_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Tenant ID required"
                    )
                
                # Check tenant access
                db = get_db_session()
                try:
                    has_access = self.rbac.check_tenant_access(
                        user["id"], tenant_id, required_role, db
                    )
                    if not has_access:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied to this tenant"
                        )
                finally:
                    db.close()
                
                return await func(request, *args, **kwargs)
            
            return wrapper
        return decorator


# Global middleware instance
auth_middleware = AuthMiddleware()