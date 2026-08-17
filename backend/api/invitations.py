"""
Pre-Registered Visitor / QR Code Invitation System.

Flow:
1. Employee/receptionist creates an invitation for an expected visitor
2. System generates a unique invitation code + QR data
3. Invitation link/QR can be sent to the visitor via email
4. On arrival, visitor presents QR code (scanned by kiosk camera or typed)
5. System validates the code and auto-creates visit (skip name/consent if pre-registered)
6. Employee is notified of arrival

Invitation states:
- PENDING: Created, not yet used
- SENT: Invitation email/notification sent to visitor
- ARRIVED: Visitor has checked in using this invitation
- EXPIRED: Past the valid_until date without check-in
- CANCELLED: Manually cancelled by creator
"""

import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from config import settings
from database.database import get_db
from database.models import Visitor, Employee, Visit
from database.repositories import (
    VisitorRepository, VisitRepository, EmployeeRepository, AuditLogRepository
)
from api.auth import require_receptionist_or_above, require_viewer_or_above

logger = structlog.get_logger()

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


# ============================================================
# In-memory invitation store (Redis-backed in production)
# ============================================================

_invitations: dict = {}


class Invitation:
    """Represents a pre-registered visitor invitation."""
    def __init__(
        self,
        invitation_id: str,
        code: str,
        visitor_name: str,
        visitor_email: Optional[str],
        visitor_company: Optional[str],
        visitor_phone: Optional[str],
        host_employee_id: str,
        host_employee_name: str,
        purpose: Optional[str],
        valid_from: datetime,
        valid_until: datetime,
        created_by: str,
    ):
        self.invitation_id = invitation_id
        self.code = code  # Short alphanumeric code (for QR / manual entry)
        self.visitor_name = visitor_name
        self.visitor_email = visitor_email
        self.visitor_company = visitor_company
        self.visitor_phone = visitor_phone
        self.host_employee_id = host_employee_id
        self.host_employee_name = host_employee_name
        self.purpose = purpose
        self.valid_from = valid_from
        self.valid_until = valid_until
        self.created_by = created_by
        self.created_at = datetime.utcnow()
        self.status = "pending"
        self.checked_in_at: Optional[datetime] = None
        self.visit_id: Optional[str] = None


# ============================================================
# Schemas
# ============================================================

class CreateInvitationRequest(BaseModel):
    """Request to create a visitor invitation."""
    visitor_name: str = Field(..., min_length=1, max_length=255)
    visitor_email: Optional[str] = Field(None, max_length=255)
    visitor_company: Optional[str] = Field(None, max_length=255)
    visitor_phone: Optional[str] = Field(None, max_length=50)
    host_employee_id: str = Field(..., description="Employee who is expecting the visitor")
    purpose: Optional[str] = Field(None, max_length=500)
    valid_from: Optional[str] = Field(None, description="ISO datetime, defaults to now")
    valid_until: Optional[str] = Field(None, description="ISO datetime, defaults to +24h")


class InvitationResponse(BaseModel):
    """Response with invitation details and QR data."""
    invitation_id: str
    code: str
    qr_data: str  # The data to encode in QR (URL or raw code)
    visitor_name: str
    host_employee_name: str
    purpose: Optional[str]
    valid_from: str
    valid_until: str
    status: str


class ValidateInvitationRequest(BaseModel):
    """Request to validate/check-in with an invitation code."""
    code: str = Field(..., min_length=6, max_length=20)


class ValidateInvitationResponse(BaseModel):
    """Response after validating an invitation."""
    valid: bool
    invitation_id: Optional[str] = None
    visitor_name: Optional[str] = None
    visitor_company: Optional[str] = None
    host_employee_name: Optional[str] = None
    purpose: Optional[str] = None
    visit_id: Optional[str] = None
    message: str


# ============================================================
# Utility
# ============================================================

def _generate_invitation_code() -> str:
    """
    Generate a short, human-readable invitation code.
    Format: XXXX-XXXX (8 alphanumeric characters, no ambiguous chars)
    """
    # Remove ambiguous characters: 0/O, 1/l/I
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code_part1 = ''.join(secrets.choice(alphabet) for _ in range(4))
    code_part2 = ''.join(secrets.choice(alphabet) for _ in range(4))
    return f"{code_part1}-{code_part2}"


def _generate_qr_data(code: str) -> str:
    """
    Generate the data string to encode in a QR code.
    Could be a URL or just the raw code depending on deployment.
    """
    # In production, this would be a URL like:
    # https://reception.codeorigin.ai/checkin?code=XXXX-XXXX
    # For now, return the code itself (kiosk can scan and validate via API)
    base_url = getattr(settings, 'invitation_base_url', '')
    if base_url:
        return f"{base_url}/checkin?code={code}"
    return f"CHECKIN:{code}"


# ============================================================
# Endpoints
# ============================================================

@router.post("/create", response_model=InvitationResponse)
async def create_invitation(
    req: CreateInvitationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_receptionist_or_above),
):
    """
    Create a pre-registration invitation for an expected visitor.
    Returns invitation code and QR data.
    """
    # Verify host employee exists
    employee_repo = EmployeeRepository(db)
    employee = await employee_repo.get_by_id(req.host_employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Host employee not found")

    # Parse validity dates
    now = datetime.utcnow()
    valid_from = datetime.fromisoformat(req.valid_from) if req.valid_from else now
    valid_until = datetime.fromisoformat(req.valid_until) if req.valid_until else now + timedelta(hours=24)

    if valid_until <= valid_from:
        raise HTTPException(status_code=400, detail="valid_until must be after valid_from")

    # Generate unique code (check for collision)
    code = _generate_invitation_code()
    attempts = 0
    while code in _invitations and attempts < 10:
        code = _generate_invitation_code()
        attempts += 1

    invitation_id = str(uuid.uuid4())

    # Create invitation
    invitation = Invitation(
        invitation_id=invitation_id,
        code=code,
        visitor_name=req.visitor_name,
        visitor_email=req.visitor_email,
        visitor_company=req.visitor_company,
        visitor_phone=req.visitor_phone,
        host_employee_id=req.host_employee_id,
        host_employee_name=employee.name,
        purpose=req.purpose,
        valid_from=valid_from,
        valid_until=valid_until,
        created_by=user["user_id"],
    )

    # Store
    _invitations[code] = invitation
    _invitations[invitation_id] = invitation

    # Audit log
    audit = AuditLogRepository(db)
    await audit.log(
        action="invitation_created",
        entity_type="invitation",
        entity_id=invitation_id,
        details=f"Visitor: {req.visitor_name}, Host: {employee.name}, Code: {code}",
        performed_by=user["user_id"],
    )
    await db.commit()

    logger.info(
        "Invitation created",
        invitation_id=invitation_id,
        code=code,
        visitor=req.visitor_name,
        host=employee.name,
    )

    return InvitationResponse(
        invitation_id=invitation_id,
        code=code,
        qr_data=_generate_qr_data(code),
        visitor_name=req.visitor_name,
        host_employee_name=employee.name,
        purpose=req.purpose,
        valid_from=valid_from.isoformat(),
        valid_until=valid_until.isoformat(),
        status="pending",
    )


@router.post("/validate", response_model=ValidateInvitationResponse)
async def validate_invitation(
    req: ValidateInvitationRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_receptionist_or_above),
):
    """
    Validate an invitation code and check in the visitor.
    Called when visitor presents QR code or types code at kiosk.
    
    On success:
    - Creates visitor record (if not exists)
    - Creates visit record
    - Notifies host employee
    - Returns visitor info for the kiosk to display
    """
    code = req.code.upper().strip()
    invitation = _invitations.get(code)

    if not invitation:
        return ValidateInvitationResponse(
            valid=False,
            message="Invalid invitation code. Please check and try again.",
        )

    # Check status
    if invitation.status == "arrived":
        return ValidateInvitationResponse(
            valid=False,
            message="This invitation has already been used.",
        )

    if invitation.status == "cancelled":
        return ValidateInvitationResponse(
            valid=False,
            message="This invitation has been cancelled.",
        )

    # Check validity window
    now = datetime.utcnow()
    if now < invitation.valid_from:
        return ValidateInvitationResponse(
            valid=False,
            message=f"This invitation is not yet valid. It starts at {invitation.valid_from.strftime('%H:%M')}.",
        )

    if now > invitation.valid_until:
        invitation.status = "expired"
        return ValidateInvitationResponse(
            valid=False,
            message="This invitation has expired. Please contact your host.",
        )

    # === VALID — Check in the visitor ===
    
    # Create or find visitor record
    visitor_repo = VisitorRepository(db)
    visit_repo = VisitRepository(db)

    # Create visitor (pre-registered visitors skip biometric consent)
    visitor = await visitor_repo.create(
        name=invitation.visitor_name,
        email=invitation.visitor_email,
        phone=invitation.visitor_phone,
        company=invitation.visitor_company,
        consent_status="pending",  # Still pending — pre-registration doesn't imply biometric consent
    )

    # Create visit record
    visit = await visit_repo.create(
        visitor_id=visitor.visitor_id,
        employee_id=invitation.host_employee_id,
        purpose=invitation.purpose,
    )

    # Mark invitation as used
    invitation.status = "arrived"
    invitation.checked_in_at = now
    invitation.visit_id = visit.visit_id

    await db.commit()

    # Notify host (async, don't block response)
    from services.notifications import notification_service
    asyncio.create_task(
        notification_service.send_visitor_arrival(
            employee_id=invitation.host_employee_id,
            employee_email=None,  # Will use webhook
            visitor_name=invitation.visitor_name,
            visitor_company=invitation.visitor_company,
            visitor_id=visitor.visitor_id,
            purpose=invitation.purpose,
        )
    )

    logger.info(
        "Invitation validated — visitor checked in",
        code=code,
        visitor=invitation.visitor_name,
        host=invitation.host_employee_name,
        visit_id=visit.visit_id,
    )

    return ValidateInvitationResponse(
        valid=True,
        invitation_id=invitation.invitation_id,
        visitor_name=invitation.visitor_name,
        visitor_company=invitation.visitor_company,
        host_employee_name=invitation.host_employee_name,
        purpose=invitation.purpose,
        visit_id=visit.visit_id,
        message=f"Welcome, {invitation.visitor_name}! {invitation.host_employee_name} has been notified of your arrival.",
    )


@router.get("/list")
async def list_invitations(
    status: Optional[str] = None,
    _user: dict = Depends(require_viewer_or_above),
):
    """List all invitations, optionally filtered by status."""
    results = []
    for key, inv in _invitations.items():
        if not isinstance(inv, Invitation):
            continue
        if key != inv.code:
            continue  # Skip duplicate entries (stored by both code and id)
        if status and inv.status != status:
            continue
        results.append({
            "invitation_id": inv.invitation_id,
            "code": inv.code,
            "visitor_name": inv.visitor_name,
            "visitor_company": inv.visitor_company,
            "host_employee_name": inv.host_employee_name,
            "purpose": inv.purpose,
            "valid_from": inv.valid_from.isoformat(),
            "valid_until": inv.valid_until.isoformat(),
            "status": inv.status,
            "checked_in_at": inv.checked_in_at.isoformat() if inv.checked_in_at else None,
        })

    return {"invitations": results, "count": len(results)}


@router.delete("/{invitation_id}")
async def cancel_invitation(
    invitation_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_receptionist_or_above),
):
    """Cancel a pending invitation."""
    invitation = _invitations.get(invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail=f"Cannot cancel invitation in '{invitation.status}' state")

    invitation.status = "cancelled"

    audit = AuditLogRepository(db)
    await audit.log(
        action="invitation_cancelled",
        entity_type="invitation",
        entity_id=invitation_id,
        performed_by=user["user_id"],
    )
    await db.commit()

    return {"message": "Invitation cancelled", "invitation_id": invitation_id}


# Need asyncio for create_task in validate
import asyncio
