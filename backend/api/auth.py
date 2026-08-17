"""
Authentication and Authorization API.
Protects dashboard and admin endpoints.
Uses JWT tokens with role-based access control.

Roles:
- ADMIN: Full access
- RECEPTIONIST: Manage visitors, view dashboard
- VIEWER: Read-only dashboard access
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
import structlog

from config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Security
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours


class UserRole:
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    VIEWER = "viewer"


# In-memory admin users (in production, use database)
# These are seeded on startup
ADMIN_USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("admin123"),  # Change in production!
        "role": UserRole.ADMIN,
        "name": "Administrator",
    },
    "receptionist": {
        "username": "receptionist",
        "hashed_password": pwd_context.hash("reception123"),  # Change in production!
        "role": UserRole.RECEPTIONIST,
        "name": "Receptionist",
    },
    "viewer": {
        "username": "viewer",
        "hashed_password": pwd_context.hash("viewer123"),  # Change in production!
        "role": UserRole.VIEWER,
        "name": "Viewer",
    },
}


# === Schemas ===

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    name: str


class UserInfo(BaseModel):
    username: str
    role: str
    name: str


# === Token Utilities ===

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return claims."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# === Dependencies ===

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Get the current authenticated user from the JWT token.
    Returns None if no valid token is provided.
    """
    if not credentials:
        return None

    payload = verify_token(credentials.credentials)
    if not payload:
        return None

    username = payload.get("sub")
    if not username or username not in ADMIN_USERS:
        return None

    return ADMIN_USERS[username]


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Require authentication — raises 401 if not authenticated."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username or username not in ADMIN_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return ADMIN_USERS[username]


async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Require ADMIN role."""
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_receptionist_or_above(user: dict = Depends(require_auth)) -> dict:
    """Require RECEPTIONIST or ADMIN role."""
    if user["role"] not in (UserRole.ADMIN, UserRole.RECEPTIONIST):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionist access required",
        )
    return user


# === Endpoints ===

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """
    Authenticate and receive a JWT token.
    """
    user = ADMIN_USERS.get(req.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not pwd_context.verify(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(
        data={"sub": user["username"], "role": user["role"]}
    )

    logger.info("User logged in", username=user["username"], role=user["role"])

    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user["role"],
        name=user["name"],
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: dict = Depends(require_auth)):
    """Get current user information."""
    return UserInfo(
        username=user["username"],
        role=user["role"],
        name=user["name"],
    )


@router.post("/logout")
async def logout():
    """
    Logout (client-side token deletion).
    JWT is stateless — client should discard the token.
    """
    return {"message": "Logged out successfully"}
