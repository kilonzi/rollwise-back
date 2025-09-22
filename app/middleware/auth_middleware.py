from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from app.models.database import get_db_session
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
security = HTTPBearer()


class RoleBasedAccessControl:
    """Role-based access control middleware and utilities"""

    # Define role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {"user": 1, "owner": 2, "platform_admin": 3}

    # Define resource permissions
    RESOURCE_PERMISSIONS = {
        "agent": {
            "read": ["user", "owner", "platform_admin"],
            "write": ["owner", "platform_admin"],
            "delete": ["owner", "platform_admin"],
        },
        "user": {
            "read": ["owner", "platform_admin"],
            "write": ["owner", "platform_admin"],
            "delete": ["platform_admin"],
        },
        "conversation": {
            "read": ["user", "owner", "platform_admin"],
            "write": ["user", "owner", "platform_admin"],
            "delete": ["owner", "platform_admin"],
        },
    }

    @staticmethod
    def get_user_from_token(token: str, db: Session) -> Optional[Dict[str, Any]]:
        """Extract user information from JWT token"""
        try:
            result = UserService.verify_token(token)
            if result:
                return result
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None

    @staticmethod
    def check_resource_permission(
        user_role: str, resource_type: str, action: str
    ) -> bool:
        """Check if user role has permission for resource action"""
        try:
            resource_perms = RoleBasedAccessControl.RESOURCE_PERMISSIONS.get(
                resource_type, {}
            )
            allowed_roles = resource_perms.get(action, [])
            return user_role in allowed_roles
        except Exception as e:
            logger.error(f"Resource permission check error: {e}")
            return False


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
                user = getattr(request.state, "user", None)
                if not user:
                    user = await self.authenticate_request(request)
                    if not user:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required",
                        )
                    request.state.user = user

                if user["global_role"] not in required_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions",
                    )

                return await func(request, *args, **kwargs)

            return wrapper

        return decorator


# Global middleware instance
auth_middleware = AuthMiddleware()
