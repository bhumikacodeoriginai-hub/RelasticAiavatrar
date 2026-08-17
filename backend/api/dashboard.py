"""
Dashboard API endpoints.
Provides management dashboard data and statistics.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.database import get_db
from database.models import Visitor, Visit, Employee, Conversation
from database.repositories import VisitorRepository, VisitRepository, EmployeeRepository

logger = structlog.get_logger()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# === Pydantic Schemas ===

class DashboardStats(BaseModel):
    """Overall dashboard statistics."""
    total_visitors_today: int
    new_visitors_today: int
    returning_visitors_today: int
    active_visitors: int
    total_registered: int
    total_employees: int
    active_conversations: int


class RecentVisitor(BaseModel):
    """A recent visitor entry for the dashboard."""
    visitor_id: str
    name: str
    company: Optional[str] = None
    arrival_time: str
    status: str
    visit_type: str  # 'new' or 'returning'


class SystemStatus(BaseModel):
    """System health status."""
    camera_active: bool
    ai_service_active: bool
    tts_active: bool
    stt_active: bool
    database_active: bool
    vision_active: bool
    websocket_active: bool
    uptime_seconds: float


# === Endpoints ===

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive dashboard statistics."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Total visits today
    total_today_result = await db.execute(
        select(func.count(Visit.visit_id))
        .where(Visit.arrival_time >= today_start)
    )
    total_today = total_today_result.scalar_one()

    # Active visitors (not departed)
    active_result = await db.execute(
        select(func.count(Visit.visit_id))
        .where(Visit.departure_time.is_(None))
    )
    active_visitors = active_result.scalar_one()

    # New visitors today (first-time)
    new_today_result = await db.execute(
        select(func.count(Visitor.visitor_id))
        .where(Visitor.created_at >= today_start)
    )
    new_today = new_today_result.scalar_one()

    # Total registered visitors
    total_registered_result = await db.execute(
        select(func.count(Visitor.visitor_id))
    )
    total_registered = total_registered_result.scalar_one()

    # Total employees
    employee_repo = EmployeeRepository(db)
    total_employees = await employee_repo.count()

    # Active conversations
    conv_manager = request.app.state.conversation_manager
    active_conversations = conv_manager.get_active_session_count()

    return DashboardStats(
        total_visitors_today=total_today,
        new_visitors_today=new_today,
        returning_visitors_today=max(0, total_today - new_today),
        active_visitors=active_visitors,
        total_registered=total_registered,
        total_employees=total_employees,
        active_conversations=active_conversations
    )


@router.get("/recent-visitors", response_model=List[RecentVisitor])
async def get_recent_visitors(
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Get recent visitors for the dashboard feed."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(Visit, Visitor)
        .join(Visitor, Visit.visitor_id == Visitor.visitor_id)
        .where(Visit.arrival_time >= today_start)
        .order_by(Visit.arrival_time.desc())
        .limit(limit)
    )
    rows = result.all()

    visitors = []
    for visit, visitor in rows:
        visit_type = "new" if visitor.visit_count <= 1 else "returning"
        visitors.append(RecentVisitor(
            visitor_id=visitor.visitor_id,
            name=visitor.name,
            company=visitor.company,
            arrival_time=visit.arrival_time.isoformat(),
            status=visit.status,
            visit_type=visit_type
        ))

    return visitors


@router.get("/system-status", response_model=SystemStatus)
async def get_system_status(request: Request):
    """Get system health status."""
    app = request.app

    # Check services
    camera_active = (
        hasattr(app.state, 'camera_service') and
        app.state.camera_service.is_running
    ) if hasattr(app.state, 'camera_service') else False

    ai_active = hasattr(app.state, 'bedrock_client') and app.state.bedrock_client._initialized
    tts_active = hasattr(app.state, 'tts') and app.state.tts._initialized
    stt_active = True  # Browser-based STT is always available
    vision_active = hasattr(app.state, 'vision_pipeline')
    websocket_active = True  # If this endpoint responds, WS is available

    db_active = True
    try:
        from database.database import check_db_health
        db_active = await check_db_health()
    except Exception:
        db_active = False

    uptime = 0.0
    if hasattr(app.state, 'start_time'):
        uptime = (datetime.utcnow() - app.state.start_time).total_seconds()

    return SystemStatus(
        camera_active=camera_active,
        ai_service_active=ai_active,
        tts_active=tts_active,
        stt_active=stt_active,
        database_active=db_active,
        vision_active=vision_active,
        websocket_active=websocket_active,
        uptime_seconds=uptime
    )
