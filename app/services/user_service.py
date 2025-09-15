import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import User, Tenant, UserTenant
from app.config.settings import settings

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = getattr(settings, 'SECRET_KEY', 'your-secret-key-here')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class UserService:
    """Service for user management and authentication"""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """Create a JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None

    @staticmethod
    def register_user(
        db: Session,
        name: str,
        email: str,
        password: str,
        phone_number: Optional[str] = None,
        tenant_id: Optional[str] = None,
        role: str = "user"
    ) -> Dict[str, Any]:
        """Register a new user"""
        try:
            # Check if user already exists
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                return {"success": False, "error": "User with this email already exists"}

            # Create new user
            user_id = str(uuid.uuid4())
            password_hash = UserService.hash_password(password)
            email_verification_token = UserService.generate_token()

            user = User(
                id=user_id,
                name=name,
                email=email,
                password_hash=password_hash,
                phone_number=phone_number,
                email_verification_token=email_verification_token
            )

            db.add(user)
            db.flush()  # Get the user ID

            created_tenant_id = None

            # If tenant_id provided, associate user with existing tenant
            if tenant_id:
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.active == True).first()
                if tenant:
                    user_tenant = UserTenant(
                        user_id=user.id,
                        tenant_id=tenant_id,
                        role=role
                    )
                    db.add(user_tenant)
            else:
                # Create default tenant for new user
                default_tenant = Tenant(
                    name=f"{name}'s Business",
                    business_type="general",
                    email=email
                )
                db.add(default_tenant)
                db.flush()  # Get the tenant ID

                # Associate user with default tenant as owner
                user_tenant = UserTenant(
                    user_id=user.id,
                    tenant_id=default_tenant.id,
                    role="owner"
                )
                db.add(user_tenant)
                created_tenant_id = default_tenant.id

            db.commit()

            response_data = {
                "success": True,
                "user_id": user.id,
                "message": "User registered successfully",
                "email_verification_token": email_verification_token
            }

            if created_tenant_id:
                response_data["tenant_id"] = created_tenant_id
                response_data["tenant_name"] = f"{name}'s Business"

            return response_data

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def login_user(db: Session, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return tokens"""
        try:
            # Find user by email
            user = db.query(User).filter(User.email == email, User.active == True).first()
            if not user:
                return {"success": False, "error": "Invalid email or password"}

            # Verify password
            if not UserService.verify_password(password, user.password_hash):
                return {"success": False, "error": "Invalid email or password"}

            # Generate tokens
            token_data = {"user_id": user.id, "email": user.email}
            access_token = UserService.create_access_token(token_data)
            refresh_token = UserService.create_refresh_token(token_data)

            # Update user with new tokens and last login
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.last_login = datetime.utcnow()
            db.commit()

            # Get user tenants and roles
            user_tenants = db.query(UserTenant).filter(
                UserTenant.user_id == user.id,
                UserTenant.active == True
            ).all()

            tenants = []
            for ut in user_tenants:
                tenant = db.query(Tenant).filter(Tenant.id == ut.tenant_id).first()
                if tenant:
                    tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "role": ut.role
                    })

            return {
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "global_role": user.global_role,
                    "tenants": tenants
                }
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def validate_token(db: Session, token: str) -> Dict[str, Any]:
        """Validate a JWT token and return user info"""
        try:
            payload = UserService.verify_token(token)
            if not payload:
                return {"success": False, "error": "Invalid token"}

            user_id = payload.get("user_id")
            if not user_id:
                return {"success": False, "error": "Invalid token payload"}

            # Find user
            user = db.query(User).filter(User.id == user_id, User.active == True).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Check if token matches stored token
            if user.access_token != token:
                return {"success": False, "error": "Token mismatch"}

            return {
                "success": True,
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "global_role": user.global_role
                }
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def request_password_reset(db: Session, email: str) -> Dict[str, Any]:
        """Generate password reset token for user"""
        try:
            user = db.query(User).filter(User.email == email, User.active == True).first()
            if not user:
                # Don't reveal if email exists
                return {"success": True, "message": "If the email exists, a reset link will be sent"}

            # Generate reset token
            reset_token = UserService.generate_token()
            reset_expires = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry

            user.reset_token = reset_token
            user.reset_token_expires = reset_expires
            db.commit()

            return {
                "success": True,
                "reset_token": reset_token,
                "message": "Password reset token generated"
            }

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def reset_password(db: Session, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Reset user password using reset token"""
        try:
            # Find user with valid reset token
            user = db.query(User).filter(
                User.reset_token == reset_token,
                User.reset_token_expires > datetime.utcnow(),
                User.active == True
            ).first()

            if not user:
                return {"success": False, "error": "Invalid or expired reset token"}

            # Update password
            user.password_hash = UserService.hash_password(new_password)
            user.reset_token = None
            user.reset_token_expires = None
            # Invalidate existing tokens
            user.access_token = None
            user.refresh_token = None
            db.commit()

            return {"success": True, "message": "Password reset successfully"}

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def add_user_to_tenant(db: Session, user_id: str, tenant_id: str, role: str = "user") -> Dict[str, Any]:
        """Add user to a tenant with specified role"""
        try:
            # Check if user exists
            user = db.query(User).filter(User.id == user_id, User.active == True).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Check if tenant exists
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.active == True).first()
            if not tenant:
                return {"success": False, "error": "Tenant not found"}

            # Check if relationship already exists
            existing = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == tenant_id
            ).first()

            if existing:
                if existing.active:
                    return {"success": False, "error": "User is already associated with this tenant"}
                else:
                    # Reactivate existing relationship
                    existing.active = True
                    existing.role = role
                    existing.updated_at = datetime.utcnow()
            else:
                # Create new relationship
                user_tenant = UserTenant(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=role
                )
                db.add(user_tenant)

            db.commit()
            return {"success": True, "message": "User added to tenant successfully"}

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def remove_user_from_tenant(db: Session, user_id: str, tenant_id: str) -> Dict[str, Any]:
        """Remove user from a tenant"""
        try:
            user_tenant = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == tenant_id,
                UserTenant.active == True
            ).first()

            if not user_tenant:
                return {"success": False, "error": "User is not associated with this tenant"}

            user_tenant.active = False
            user_tenant.updated_at = datetime.utcnow()
            db.commit()

            return {"success": True, "message": "User removed from tenant successfully"}

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_user_tenants(db: Session, user_id: str) -> Dict[str, Any]:
        """Get all tenants associated with a user"""
        try:
            user_tenants = db.query(UserTenant).filter(
                UserTenant.user_id == user_id,
                UserTenant.active == True
            ).all()

            tenants = []
            for ut in user_tenants:
                tenant = db.query(Tenant).filter(Tenant.id == ut.tenant_id, Tenant.active == True).first()
                if tenant:
                    tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "business_type": tenant.business_type,
                        "role": ut.role,
                        "joined_at": ut.created_at.isoformat()
                    })

            return {
                "success": True,
                "tenants": tenants,
                "count": len(tenants)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_tenant_users(db: Session, tenant_id: str) -> Dict[str, Any]:
        """Get all users associated with a tenant"""
        try:
            user_tenants = db.query(UserTenant).filter(
                UserTenant.tenant_id == tenant_id,
                UserTenant.active == True
            ).all()

            users = []
            for ut in user_tenants:
                user = db.query(User).filter(User.id == ut.user_id, User.active == True).first()
                if user:
                    users.append({
                        "user_id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "phone_number": user.phone_number,
                        "role": ut.role,
                        "joined_at": ut.created_at.isoformat(),
                        "last_login": user.last_login.isoformat() if user.last_login else None
                    })

            return {
                "success": True,
                "users": users,
                "count": len(users)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}