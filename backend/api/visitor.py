"""
Visitor API endpoints.
Handles visitor registration, lookup, consent management, and visit tracking.
"""

from typing import Optional, List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.database import get_db
from database.repositories import VisitorRepository, VisitRepository
from database.models import ConsentStatus

logger = structlog.get_logger()

router = APIRouter(prefix="/api/visitors", tags=["visitors"])


# === Pydantic Schemas ===

class VisitorCreate(BaseModel):
    """Schema for creating a new visitor."""
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    consent_status: str = Field(default="pending")
    face_embedding: Optional[List[float]] = None


class VisitorResponse(BaseModel):
    """Schema for visitor response."""
    visitor_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    consent_status: str
    visit_count: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class VisitCreate(BaseModel):
    """Schema for creating a new visit."""
    visitor_id: str
    employee_id: Optional[str] = None
    purpose: Optional[str] = None


class VisitResponse(BaseModel):
    """Schema for visit response."""
    visit_id: str
    visitor_id: str
    arrival_time: str
    departure_time: Optional[str] = None
    purpose: Optional[str] = None
    status: str

    class Config:
        from_attributes = True


class ConsentUpdate(BaseModel):
    """Schema for updating consent status."""
    consent_status: str = Field(..., pattern="^(granted|denied|revoked)$")


class VisitorStats(BaseModel):
    """Schema for visitor statistics."""
    visits_today: int
    active_visitors: int
    total_registered: int


# === Endpoints ===

@router.post("/register", response_model=VisitorResponse)
async def register_visitor(
    visitor: VisitorCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new visitor.
    Called after consent is granted and name is captured.
    """
    repo = VisitorRepository(db)

    # Convert face embedding if provided
    embedding = None
    if visitor.face_embedding:
        if len(visitor.face_embedding) != 512:
            raise HTTPException(
                status_code=400,
                detail="Face embedding must be exactly 512 dimensions"
            )
        embedding = np.array(visitor.face_embedding, dtype=np.float32)

    # Validate consent: never store embedding without explicit consent
    if embedding is not None and visitor.consent_status != ConsentStatus.GRANTED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot store face embedding without granted consent"
        )

    person = await repo.create(
        name=visitor.name,
        face_embedding=embedding,
        email=visitor.email,
        phone=visitor.phone,
        company=visitor.company,
        role=visitor.role,
        consent_status=visitor.consent_status
    )

    await db.commit()
    logger.info("Visitor registered", visitor_id=person.visitor_id, name=person.name)

    return VisitorResponse(
        visitor_id=person.visitor_id,
        name=person.name,
        email=person.email,
        phone=person.phone,
        company=person.company,
        role=person.role,
        consent_status=person.consent_status,
        visit_count=person.visit_count,
        first_seen=person.first_seen.isoformat() if person.first_seen else None,
        last_seen=person.last_seen.isoformat() if person.last_seen else None,
        created_at=person.created_at.isoformat()
    )


@router.get("/", response_model=List[VisitorResponse])
async def list_visitors(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List all registered visitors with pagination."""
    repo = VisitorRepository(db)
    visitors = await repo.get_all(limit=limit, offset=offset)

    return [
        VisitorResponse(
            visitor_id=v.visitor_id,
            name=v.name,
            email=v.email,
            phone=v.phone,
            company=v.company,
            role=v.role,
            consent_status=v.consent_status,
            visit_count=v.visit_count,
            first_seen=v.first_seen.isoformat() if v.first_seen else None,
            last_seen=v.last_seen.isoformat() if v.last_seen else None,
            created_at=v.created_at.isoformat()
        )
        for v in visitors
    ]


@router.get("/stats", response_model=VisitorStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get visitor statistics for the dashboard."""
    repo = VisitorRepository(db)
    stats = await repo.get_stats()
    return VisitorStats(**stats)


@router.get("/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(
    visitor_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific visitor by ID."""
    repo = VisitorRepository(db)
    visitor = await repo.get_by_id(visitor_id)

    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    return VisitorResponse(
        visitor_id=visitor.visitor_id,
        name=visitor.name,
        email=visitor.email,
        phone=visitor.phone,
        company=visitor.company,
        role=visitor.role,
        consent_status=visitor.consent_status,
        visit_count=visitor.visit_count,
        first_seen=visitor.first_seen.isoformat() if visitor.first_seen else None,
        last_seen=visitor.last_seen.isoformat() if visitor.last_seen else None,
        created_at=visitor.created_at.isoformat()
    )


@router.put("/{visitor_id}/consent", response_model=dict)
async def update_consent(
    visitor_id: str,
    consent: ConsentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update visitor consent status.
    If revoked, removes face embedding and image data (GDPR compliance).
    """
    repo = VisitorRepository(db)
    visitor = await repo.get_by_id(visitor_id)

    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    if consent.consent_status == ConsentStatus.REVOKED.value:
        await repo.revoke_consent(visitor_id)
        await db.commit()
        return {"message": "Consent revoked. Biometric data has been deleted."}
    else:
        await repo.update_consent(visitor_id, consent.consent_status)
        await db.commit()
        return {"message": f"Consent status updated to: {consent.consent_status}"}


@router.delete("/{visitor_id}")
async def delete_visitor(
    visitor_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a visitor and all associated data.
    This is a permanent action for privacy/GDPR compliance.
    """
    repo = VisitorRepository(db)
    success = await repo.delete(visitor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Visitor not found")

    await db.commit()
    return {"message": "Visitor and all associated data have been deleted."}


@router.post("/visits", response_model=VisitResponse)
async def create_visit(
    visit: VisitCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new visit record."""
    visit_repo = VisitRepository(db)

    new_visit = await visit_repo.create(
        visitor_id=visit.visitor_id,
        employee_id=visit.employee_id,
        purpose=visit.purpose
    )

    await db.commit()

    return VisitResponse(
        visit_id=new_visit.visit_id,
        visitor_id=new_visit.visitor_id,
        arrival_time=new_visit.arrival_time.isoformat(),
        departure_time=None,
        purpose=new_visit.purpose,
        status=new_visit.status
    )


@router.put("/visits/{visit_id}/end")
async def end_visit(
    visit_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Mark a visit as ended/departed."""
    visit_repo = VisitRepository(db)
    await visit_repo.end_visit(visit_id)
    await db.commit()
    return {"message": "Visit ended successfully"}


@router.get("/visits/active", response_model=List[VisitResponse])
async def get_active_visits(db: AsyncSession = Depends(get_db)):
    """Get all currently active visits."""
    visit_repo = VisitRepository(db)
    visits = await visit_repo.get_active_visits()

    return [
        VisitResponse(
            visit_id=v.visit_id,
            visitor_id=v.visitor_id,
            arrival_time=v.arrival_time.isoformat(),
            departure_time=v.departure_time.isoformat() if v.departure_time else None,
            purpose=v.purpose,
            status=v.status
        )
        for v in visits
    ]
