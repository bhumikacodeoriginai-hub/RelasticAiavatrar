"""
Visitor Badge Generation API.
Generates badge data for printing or display.

Badge contains:
- Visitor name
- Visitor company
- Host employee name
- Date of visit
- Badge number (sequential)
- Expiry time
- QR code data (for badge scanning on exit)

Output format: JSON data structure (frontend/printer renders actual badge).
For production: integrate with badge printer API or generate PDF.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.database import get_db
from database.repositories import VisitorRepository, VisitRepository, EmployeeRepository
from api.auth import require_receptionist_or_above

logger = structlog.get_logger()

router = APIRouter(prefix="/api/badges", tags=["badges"])

# Sequential badge counter (in production: database-backed)
_badge_counter = 1000


class GenerateBadgeRequest(BaseModel):
    """Request to generate a visitor badge."""
    visitor_id: str
    visit_id: str
    host_employee_id: Optional[str] = None


class BadgeData(BaseModel):
    """Badge data for rendering/printing."""
    badge_number: str
    visitor_name: str
    visitor_company: Optional[str]
    host_name: Optional[str]
    host_department: Optional[str]
    purpose: Optional[str]
    issue_date: str
    issue_time: str
    expiry_time: str
    qr_data: str
    badge_type: str  # visitor, contractor, interview, vip


@router.post("/generate", response_model=BadgeData)
async def generate_badge(
    req: GenerateBadgeRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_receptionist_or_above),
):
    """
    Generate badge data for a visitor.
    Returns structured data for the frontend/printer to render.
    """
    global _badge_counter

    visitor_repo = VisitorRepository(db)
    visit_repo = VisitRepository(db)
    employee_repo = EmployeeRepository(db)

    # Fetch visitor
    visitor = await visitor_repo.get_by_id(req.visitor_id)
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    # Fetch host employee (optional)
    host_name = None
    host_department = None
    if req.host_employee_id:
        employee = await employee_repo.get_by_id(req.host_employee_id)
        if employee:
            host_name = employee.name
            host_department = employee.department

    # Generate badge number
    _badge_counter += 1
    badge_number = f"V-{_badge_counter:06d}"

    # Determine badge type
    badge_type = "visitor"  # Could be extended: contractor, interview, vip

    # Times
    now = datetime.utcnow()
    expiry = now + timedelta(hours=8)  # Badge valid for 8 hours

    # QR data for badge scanning (check-out validation)
    qr_data = f"BADGE:{badge_number}|VIS:{req.visitor_id}|VISIT:{req.visit_id}"

    badge = BadgeData(
        badge_number=badge_number,
        visitor_name=visitor.name,
        visitor_company=visitor.company,
        host_name=host_name,
        host_department=host_department,
        purpose=None,  # Could fetch from visit
        issue_date=now.strftime("%Y-%m-%d"),
        issue_time=now.strftime("%H:%M"),
        expiry_time=expiry.strftime("%H:%M"),
        qr_data=qr_data,
        badge_type=badge_type,
    )

    logger.info("Badge generated", badge_number=badge_number, visitor=visitor.name)

    return badge


@router.get("/verify/{badge_number}")
async def verify_badge(
    badge_number: str,
    _user: dict = Depends(require_receptionist_or_above),
):
    """
    Verify a badge is valid (for security checkpoint scanning).
    In production: check against database of issued badges.
    """
    # Basic format validation
    if not badge_number.startswith("V-"):
        return {"valid": False, "message": "Invalid badge format"}

    # In production: lookup badge in database, check expiry
    return {
        "valid": True,
        "badge_number": badge_number,
        "message": "Badge format valid (full validation requires DB lookup)",
    }
