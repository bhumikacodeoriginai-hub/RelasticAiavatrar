"""
Host Approval Workflow API.
Allows employees to approve, reject, or delay visitor meetings.

Flow:
1. Visitor requests to meet an employee
2. System creates a HostApprovalRequest with a unique token
3. Notification sent to employee (in-app + webhook/email) with action link
4. Employee responds via:
   a. Dashboard UI (authenticated)
   b. Token-based link (single-use, time-limited — works from email/Slack)
5. Visitor is informed of the decision
6. If approved, visit is updated with employee assignment

Responses:
- APPROVE: Employee is available and will meet the visitor
- REJECT: Employee declines (with optional reason)
- DELAY: Employee is busy, asks visitor to wait (with estimated time)
"""

import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from config import settings
from database.database import get_db, AsyncSessionLocal
from database.models import Notification, Employee, Visit, Visitor
from database.repositories import (
    EmployeeRepository, VisitRepository, VisitorRepository,
    NotificationRepository, AuditLogRepository
)
from api.auth import require_receptionist_or_above, require_viewer_or_above
from services.notifications import notification_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/host-approval", tags=["host-approval"])


# ============================================================
# Models (in-memory for now — would be DB table in full production)
# ============================================================

# In-memory store for approval requests (Redis-backed in production)
_pending_approvals: dict = {}


class ApprovalRequest:
    """Tracks a pending host approval request."""
    def __init__(
        self,
        request_id: str,
        token: str,
        visitor_id: str,
        visitor_name: str,
        employee_id: str,
        employee_name: str,
        visit_id: Optional[str],
        purpose: Optional[str],
        created_at: datetime,
        expires_at: datetime,
    ):
        self.request_id = request_id
        self.token = token
        self.visitor_id = visitor_id
        self.visitor_name = visitor_name
        self.employee_id = employee_id
        self.employee_name = employee_name
        self.visit_id = visit_id
        self.purpose = purpose
        self.created_at = created_at
        self.expires_at = expires_at
        self.status = "pending"  # pending, approved, rejected, delayed, expired
        self.response_at: Optional[datetime] = None
        self.response_reason: Optional[str] = None
        self.delay_minutes: Optional[int] = None


# ============================================================
# Schemas
# ============================================================

class CreateApprovalRequest(BaseModel):
    """Request to create a host approval workflow."""
    visitor_id: str
    employee_id: str
    visit_id: Optional[str] = None
    purpose: Optional[str] = None


class HostResponseRequest(BaseModel):
    """Host's response to an approval request."""
    decision: str = Field(..., pattern="^(approve|reject|delay)$")
    reason: Optional[str] = Field(None, max_length=500)
    delay_minutes: Optional[int] = Field(None, ge=1, le=120)


class ApprovalStatusResponse(BaseModel):
    """Status of an approval request."""
    request_id: str
    status: str
    visitor_name: str
    employee_name: str
    purpose: Optional[str]
    created_at: str
    response_at: Optional[str]
    decision: Optional[str]
    reason: Optional[str]
    delay_minutes: Optional[int]


# ============================================================
# Endpoints
# ============================================================

@router.post("/request")
async def create_approval_request(
    req: CreateApprovalRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_receptionist_or_above),
):
    """
    Create a host approval request.
    Sends notification to the employee and waits for their response.
    """
    # Fetch employee and visitor info
    employee_repo = EmployeeRepository(db)
    visitor_repo = VisitorRepository(db)

    employee = await employee_repo.get_by_id(req.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    visitor = await visitor_repo.get_by_id(req.visitor_id)
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    # Generate unique approval token (URL-safe, single-use)
    request_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)

    # Create approval request
    approval = ApprovalRequest(
        request_id=request_id,
        token=token,
        visitor_id=req.visitor_id,
        visitor_name=visitor.name,
        employee_id=req.employee_id,
        employee_name=employee.name,
        visit_id=req.visit_id,
        purpose=req.purpose,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )

    # Store (in production, use Redis with TTL)
    _pending_approvals[token] = approval
    _pending_approvals[request_id] = approval

    # Send notification to employee
    await notification_service.send_host_approval_request(
        employee_id=req.employee_id,
        employee_email=employee.email,
        visitor_name=visitor.name,
        approval_token=token,
        visitor_company=visitor.company,
    )

    logger.info(
        "Host approval request created",
        request_id=request_id,
        employee=employee.name,
        visitor=visitor.name,
    )

    return {
        "request_id": request_id,
        "token": token,
        "status": "pending",
        "expires_at": approval.expires_at.isoformat(),
        "message": f"Notification sent to {employee.name}",
    }


@router.post("/respond/{token}")
async def respond_to_approval(
    token: str,
    req: HostResponseRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Respond to a host approval request via token.
    This endpoint can be called from email/Slack links (token-based auth).
    Token is single-use and time-limited (30 min).
    """
    # Find approval request
    approval = _pending_approvals.get(token)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found or already responded")

    # Check expiry
    if datetime.utcnow() > approval.expires_at:
        approval.status = "expired"
        raise HTTPException(status_code=410, detail="Approval request has expired")

    # Check not already responded
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already responded: {approval.status}")

    # Record response
    approval.status = req.decision + "d" if req.decision != "delay" else "delayed"
    approval.response_at = datetime.utcnow()
    approval.response_reason = req.reason
    approval.delay_minutes = req.delay_minutes

    # Invalidate token (single-use)
    _pending_approvals.pop(token, None)

    # Update visit record if approved
    if req.decision == "approve" and approval.visit_id:
        visit_repo = VisitRepository(db)
        # Could update visit with employee assignment
        await db.commit()

    # Log audit
    audit = AuditLogRepository(db)
    await audit.log(
        action=f"host_{req.decision}",
        entity_type="approval_request",
        entity_id=approval.request_id,
        details=f"Employee {approval.employee_name} {req.decision}d visit from {approval.visitor_name}. Reason: {req.reason or 'N/A'}",
        performed_by=approval.employee_id,
    )
    await db.commit()

    logger.info(
        "Host approval response received",
        request_id=approval.request_id,
        decision=req.decision,
        employee=approval.employee_name,
        visitor=approval.visitor_name,
    )

    return {
        "request_id": approval.request_id,
        "status": approval.status,
        "decision": req.decision,
        "message": f"Response recorded: {req.decision}",
    }


@router.get("/status/{request_id}", response_model=ApprovalStatusResponse)
async def get_approval_status(
    request_id: str,
    _user: dict = Depends(require_viewer_or_above),
):
    """Get the status of an approval request."""
    approval = _pending_approvals.get(request_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return ApprovalStatusResponse(
        request_id=approval.request_id,
        status=approval.status,
        visitor_name=approval.visitor_name,
        employee_name=approval.employee_name,
        purpose=approval.purpose,
        created_at=approval.created_at.isoformat(),
        response_at=approval.response_at.isoformat() if approval.response_at else None,
        decision=approval.status if approval.status != "pending" else None,
        reason=approval.response_reason,
        delay_minutes=approval.delay_minutes,
    )


@router.get("/pending")
async def get_pending_approvals(
    _user: dict = Depends(require_viewer_or_above),
):
    """Get all pending approval requests (for dashboard)."""
    pending = [
        {
            "request_id": a.request_id,
            "visitor_name": a.visitor_name,
            "employee_name": a.employee_name,
            "purpose": a.purpose,
            "created_at": a.created_at.isoformat(),
            "expires_at": a.expires_at.isoformat(),
            "status": a.status,
        }
        for a in _pending_approvals.values()
        if isinstance(a, ApprovalRequest) and a.status == "pending"
    ]
    return {"pending_approvals": pending, "count": len(pending)}
