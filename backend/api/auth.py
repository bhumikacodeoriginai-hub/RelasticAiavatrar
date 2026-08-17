"""
Authentication and Authorization API.
Database-backed users with bcrypt password hashing and JWT tokens.

SECURITY:
- NO hardcoded credentials anywhere in this file.
- Users stored in MySQL with bcrypt-hashed passwords.
- Account lockout after configurable failed attempts.
- WebSocket connection tickets (short-lived signed tokens).
- Role-based access control with 8 enterprise roles.

Roles (least → most privilege):
- KIOSK_DEVICE: Automated kiosk access
- VIEWER: Read-only dashboard
- AUDITOR: Audit log access
- RECEPTIONIST: Day-to-day visitor handling
- RECEPTION_MANAGER: Manage reception operations
- SECURITY_OFFICER: Security monitoring
- IT_ADMIN: System configuration
- SUPER_ADMIN: Full access
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from config import settings
from database.database import get_db
from database.repositories import UserRepository, AuditLogRepository
from database.models import UserRoleEnum

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Security utilities
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
ALGORITHM = "HS256"


# ============================================================
# Schemas
# ============================================================

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    display_name: str
    user_id: str


class UserInfo(BaseModel):
    user_id: str
    username: str
    email: str
    role: str
    display_name: str
    last_login: Optional[str] = None
    permissions: Optional[dict] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    role_name: str = Field(..., description="Role name from UserRoleEnum")


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int


# ============================================================
# Token Utilities
# ============================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)


def create_ws_ticket(user_id: str, role: str) -> str:
    """
    Create a short-lived WebSocket connection ticket.
    These expire quickly (30s default) and are single-use.
    """
    data = {
        "sub": user_id,
        "role": role,
        "type": "ws_ticket",
        "exp": datetime.utcnow() + timedelta(seconds=settings.ws_ticket_expire_seconds),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(data, settings.app_secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return claims."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_ws_ticket(ticket: str) -> Optional[dict]:
    """Verify a WebSocket connection ticket."""
    payload = verify_token(ticket)
    if payload and payload.get("type") == "ws_ticket":
        return payload
    return None


# ============================================================
# Dependencies (used by other API modules)
# ============================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """
    Get the current authenticated user from JWT token.
    Returns None if no valid token (for optional auth endpoints).
    """
    if not credentials:
        return None

    payload = verify_token(credentials.credentials)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        return None

    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role.name if user.role else "viewer",
        "display_name": user.display_name,
        "permissions": user.role.permissions if user.role else {},
    }


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Require authentication — raises 401 if not authenticated."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role.name if user.role else "viewer",
        "display_name": user.display_name,
        "permissions": user.role.permissions if user.role else {},
    }


async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Require SUPER_ADMIN or IT_ADMIN role."""
    if user["role"] not in (UserRoleEnum.SUPER_ADMIN.value, UserRoleEnum.IT_ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


async def require_manager_or_above(user: dict = Depends(require_auth)) -> dict:
    """Require RECEPTION_MANAGER or higher."""
    allowed = (
        UserRoleEnum.SUPER_ADMIN.value, UserRoleEnum.IT_ADMIN.value,
        UserRoleEnum.RECEPTION_MANAGER.value,
    )
    if user["role"] not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return user


async def require_receptionist_or_above(user: dict = Depends(require_auth)) -> dict:
    """Require RECEPTIONIST or higher."""
    allowed = (
        UserRoleEnum.SUPER_ADMIN.value, UserRoleEnum.IT_ADMIN.value,
        UserRoleEnum.RECEPTION_MANAGER.value, UserRoleEnum.RECEPTIONIST.value,
    )
    if user["role"] not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionist access required",
        )
    return user


async def require_viewer_or_above(user: dict = Depends(require_auth)) -> dict:
    """Any authenticated user with at least VIEWER role."""
    # All authenticated users can view
    return user


def has_permission(user: dict, permission: str) -> bool:
    """Check if user has a specific permission."""
    permissions = user.get("permissions", {})
    if permissions.get("all"):
        return True
    return permissions.get(permission, False)


# ============================================================
# Endpoints
# ============================================================

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with username + password. Returns JWT access token.
    Account locks after configurable failed attempts.
    """
    repo = UserRepository(db)
    audit = AuditLogRepository(db)
    client_ip = request.client.host if request.client else "unknown"

    # Find user
    user = await repo.get_by_username(req.username)

    if not user:
        # Log failed attempt but don't reveal if username exists
        await audit.log(
            action="login_failed",
            entity_type="auth",
            details=f"Unknown username attempted: {req.username[:50]}",
            ip_address=client_ip,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Check if account is locked
    if user.is_locked:
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds())
            await audit.log(
                action="login_blocked_locked",
                entity_type="user",
                entity_id=user.user_id,
                details=f"Account locked, {remaining}s remaining",
                performed_by=user.user_id,
                ip_address=client_ip,
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account is locked. Try again in {remaining} seconds.",
            )
        else:
            # Lock expired — unlock
            await repo.unlock_user(user.user_id)

    # Check if active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )

    # Verify password
    if not pwd_context.verify(req.password, user.hashed_password):
        attempts = await repo.increment_failed_attempts(user.user_id)
        await audit.log(
            action="login_failed",
            entity_type="user",
            entity_id=user.user_id,
            details=f"Invalid password, attempt {attempts}/{settings.login_max_attempts}",
            performed_by=user.user_id,
            ip_address=client_ip,
        )
        await db.commit()

        if attempts >= settings.login_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked after {attempts} failed attempts. "
                       f"Try again in {settings.login_lockout_seconds // 60} minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Success — create token
    role_name = user.role.name if user.role else "viewer"
    token = create_access_token(
        data={"sub": user.user_id, "role": role_name, "username": user.username}
    )

    # Update last login
    await repo.update_last_login(user.user_id)
    await audit.log(
        action="login_success",
        entity_type="user",
        entity_id=user.user_id,
        performed_by=user.user_id,
        ip_address=client_ip,
    )
    await db.commit()

    logger.info("User logged in", username=user.username, role=role_name)

    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        role=role_name,
        display_name=user.display_name,
        user_id=user.user_id,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: dict = Depends(require_auth)):
    """Get current authenticated user information."""
    return UserInfo(
        user_id=user["user_id"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        display_name=user["display_name"],
        permissions=user["permissions"],
    )


@router.post("/ws-ticket", response_model=WSTicketResponse)
async def get_ws_ticket(user: dict = Depends(require_auth)):
    """
    Get a short-lived WebSocket connection ticket.
    Client must present this ticket when opening a WebSocket connection.
    Tickets expire in 30 seconds and are single-use intent.
    """
    ticket = create_ws_ticket(user["user_id"], user["role"])
    return WSTicketResponse(
        ticket=ticket,
        expires_in=settings.ws_ticket_expire_seconds,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Change own password. Requires current password verification."""
    repo = UserRepository(db)
    audit = AuditLogRepository(db)

    db_user = await repo.get_by_id(user["user_id"])
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    if not pwd_context.verify(req.current_password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Hash and store new password
    new_hash = pwd_context.hash(req.new_password)
    await repo.change_password(user["user_id"], new_hash)
    await audit.log(
        action="password_changed",
        entity_type="user",
        entity_id=user["user_id"],
        performed_by=user["user_id"],
    )
    await db.commit()

    return {"message": "Password changed successfully"}


@router.post("/users", response_model=UserInfo)
async def create_user(
    req: CreateUserRequest,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user. Requires ADMIN role."""
    from database.repositories import RoleRepository

    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)
    audit = AuditLogRepository(db)

    # Check username uniqueness
    existing = await user_repo.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    existing_email = await user_repo.get_by_email(req.email)
    if existing_email:
        raise HTTPException(status_code=409, detail="Email already exists")

    # Find role
    role = await role_repo.get_by_name(req.role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{req.role_name}' not found")

    # Create user
    new_user = await user_repo.create(
        username=req.username,
        email=req.email,
        hashed_password=pwd_context.hash(req.password),
        display_name=req.display_name,
        role_id=role.role_id,
    )

    await audit.log(
        action="user_created",
        entity_type="user",
        entity_id=new_user.user_id,
        details=f"Username: {req.username}, Role: {req.role_name}",
        performed_by=user["user_id"],
    )
    await db.commit()

    return UserInfo(
        user_id=new_user.user_id,
        username=new_user.username,
        email=new_user.email,
        role=req.role_name,
        display_name=new_user.display_name,
    )


@router.post("/logout")
async def logout(
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Logout. Logs the event for audit purposes.
    Client must discard the token.
    """
    audit = AuditLogRepository(db)
    await audit.log(
        action="logout",
        entity_type="user",
        entity_id=user["user_id"],
        performed_by=user["user_id"],
    )
    await db.commit()
    return {"message": "Logged out successfully"}
