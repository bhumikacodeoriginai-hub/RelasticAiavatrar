"""
Database seed utility.
Creates initial roles and the first admin user if the database is empty.

SECURITY:
- Initial admin password MUST come from environment variable INITIAL_ADMIN_PASSWORD.
- If not provided, a random password is generated and logged ONCE at startup.
- This is only used for first-time setup.
"""

import secrets
import uuid
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from config import settings
from database.models import User, Role, UserRoleEnum

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Default role definitions with permissions
DEFAULT_ROLES = [
    {
        "name": UserRoleEnum.SUPER_ADMIN.value,
        "display_name": "Super Administrator",
        "description": "Full system access including user management and configuration",
        "permissions": {"all": True},
        "is_system": True,
    },
    {
        "name": UserRoleEnum.IT_ADMIN.value,
        "display_name": "IT Administrator",
        "description": "System configuration, device management, integrations",
        "permissions": {
            "users.read": True, "users.create": True, "users.update": True,
            "devices.manage": True, "config.manage": True,
            "visitors.read": True, "employees.read": True,
            "dashboard.read": True, "audit.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.SECURITY_OFFICER.value,
        "display_name": "Security Officer",
        "description": "Security monitoring, audit review, incident response",
        "permissions": {
            "audit.read": True, "audit.export": True,
            "visitors.read": True, "visits.read": True,
            "security_events.read": True, "security_events.manage": True,
            "dashboard.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.RECEPTION_MANAGER.value,
        "display_name": "Reception Manager",
        "description": "Manage reception operations, visitor policies, staff",
        "permissions": {
            "visitors.read": True, "visitors.create": True, "visitors.update": True, "visitors.delete": True,
            "visits.read": True, "visits.manage": True,
            "employees.read": True, "employees.update": True,
            "appointments.read": True, "appointments.manage": True,
            "notifications.manage": True,
            "dashboard.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.RECEPTIONIST.value,
        "display_name": "Receptionist",
        "description": "Day-to-day visitor handling and check-in/check-out",
        "permissions": {
            "visitors.read": True, "visitors.create": True, "visitors.update": True,
            "visits.read": True, "visits.manage": True,
            "employees.read": True,
            "appointments.read": True,
            "notifications.read": True,
            "dashboard.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.AUDITOR.value,
        "display_name": "Auditor",
        "description": "Read-only access to audit logs and compliance data",
        "permissions": {
            "audit.read": True, "audit.export": True,
            "visitors.read": True, "visits.read": True,
            "dashboard.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.VIEWER.value,
        "display_name": "Viewer",
        "description": "Read-only dashboard access",
        "permissions": {
            "dashboard.read": True,
            "visitors.read": True,
            "visits.read": True,
        },
        "is_system": True,
    },
    {
        "name": UserRoleEnum.KIOSK_DEVICE.value,
        "display_name": "Kiosk Device",
        "description": "Automated kiosk/device access for visitor interaction",
        "permissions": {
            "kiosk.operate": True,
            "visitors.create": True,
            "visits.manage": True,
            "conversation.manage": True,
            "ws.connect": True,
        },
        "is_system": True,
    },
]


async def seed_roles(db: AsyncSession) -> dict:
    """
    Create default roles if they don't exist.
    Returns dict mapping role name → role_id.
    """
    role_map = {}
    for role_def in DEFAULT_ROLES:
        existing = await db.execute(
            select(Role).where(Role.name == role_def["name"])
        )
        role = existing.scalar_one_or_none()

        if role is None:
            role = Role(
                role_id=str(uuid.uuid4()),
                name=role_def["name"],
                display_name=role_def["display_name"],
                description=role_def["description"],
                permissions=role_def["permissions"],
                is_system=role_def["is_system"],
            )
            db.add(role)
            logger.info("Created role", role=role_def["name"])

        role_map[role_def["name"]] = role.role_id if hasattr(role, 'role_id') else role_def["name"]

    await db.flush()

    # Re-fetch to get actual IDs
    result = await db.execute(select(Role))
    for role in result.scalars().all():
        role_map[role.name] = role.role_id

    return role_map


async def seed_initial_admin(db: AsyncSession, role_map: dict) -> None:
    """
    Create the initial admin user if no users exist.
    Password comes from INITIAL_ADMIN_PASSWORD env var.
    If not set, generates a random password and logs it ONCE.
    """
    # Check if any users exist
    user_count = await db.execute(select(func.count(User.user_id)))
    count = user_count.scalar_one()

    if count > 0:
        logger.info("Users already exist, skipping initial admin seed", user_count=count)
        return

    # Determine password
    admin_password = settings.initial_admin_password
    password_was_generated = False

    if not admin_password or admin_password.strip() == "":
        # Generate a secure random password
        admin_password = secrets.token_urlsafe(16)
        password_was_generated = True

    # Get super_admin role ID
    admin_role_id = role_map.get(UserRoleEnum.SUPER_ADMIN.value)
    if not admin_role_id:
        logger.error("Super admin role not found — cannot create initial admin")
        return

    # Create admin user
    admin_user = User(
        user_id=str(uuid.uuid4()),
        username=settings.initial_admin_username,
        email=settings.initial_admin_email,
        hashed_password=pwd_context.hash(admin_password),
        display_name="System Administrator",
        role_id=admin_role_id,
        is_active=True,
        password_changed_at=datetime.utcnow(),
    )
    db.add(admin_user)
    await db.flush()

    if password_was_generated:
        logger.warning(
            "=" * 60 + "\n"
            "  INITIAL ADMIN CREATED WITH GENERATED PASSWORD\n"
            f"  Username: {settings.initial_admin_username}\n"
            f"  Password: {admin_password}\n"
            "  ⚠️  CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN\n"
            "  Set INITIAL_ADMIN_PASSWORD env var to avoid this.\n"
            + "=" * 60
        )
    else:
        logger.info(
            "Initial admin user created",
            username=settings.initial_admin_username,
            email=settings.initial_admin_email,
        )


async def run_seeds(db: AsyncSession) -> None:
    """Run all database seeds."""
    logger.info("Running database seeds...")
    role_map = await seed_roles(db)
    await seed_initial_admin(db, role_map)
    await db.commit()
    logger.info("Database seeds completed")
