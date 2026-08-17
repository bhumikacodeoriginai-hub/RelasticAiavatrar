"""
Visit Lifecycle Management API.
Handles visit check-in, check-out, departure detection, and session termination.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.database import get_db, AsyncSessionLocal
from database.repositories import VisitRepository, VisitorRepository, ConversationRepository
from database.models import VisitStatus
from config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/api/visits", tags=["visits"])


# === Schemas ===

class ActiveVisitResponse(BaseModel):
    visit_id: str
    visitor_id: str
    visitor_name: str
    arrival_time: str
    duration_minutes: int
    status: str
    employee_id: Optional[str] = None
    purpose: Optional[str] = None


class VisitStatsResponse(BaseModel):
    total_today: int
    active_now: int
    average_duration_minutes: float
    peak_hour: Optional[int] = None
    new_visitors_today: int
    returning_visitors_today: int


# === Endpoints ===

@router.get("/active", response_model=List[ActiveVisitResponse])
async def get_active_visits(db: AsyncSession = Depends(get_db)):
    """Get all currently active visits with visitor details."""
    visit_repo = VisitRepository(db)
    visitor_repo = VisitorRepository(db)
    active_visits = await visit_repo.get_active_visits()

    results = []
    now = datetime.utcnow()
    for visit in active_visits:
        visitor = await visitor_repo.get_by_id(visit.visitor_id)
        duration = int((now - visit.arrival_time).total_seconds() / 60)
        results.append(ActiveVisitResponse(
            visit_id=visit.visit_id,
            visitor_id=visit.visitor_id,
            visitor_name=visitor.name if visitor else "Unknown",
            arrival_time=visit.arrival_time.isoformat(),
            duration_minutes=duration,
            status=visit.status,
            employee_id=visit.employee_id,
            purpose=visit.purpose,
        ))

    return results


@router.post("/{visit_id}/depart")
async def mark_departure(
    visit_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Manually mark a visit as departed."""
    visit_repo = VisitRepository(db)
    await visit_repo.end_visit(visit_id)
    await db.commit()
    logger.info("Visit manually marked as departed", visit_id=visit_id)
    return {"message": "Visit marked as departed", "departure_time": datetime.utcnow().isoformat()}


@router.get("/stats/today", response_model=VisitStatsResponse)
async def get_today_stats(db: AsyncSession = Depends(get_db)):
    """Get today's visit statistics including peak hours."""
    from sqlalchemy import select, func, and_, extract
    from database.models import Visit, Visitor

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Total today
    total_result = await db.execute(
        select(func.count(Visit.visit_id))
        .where(Visit.arrival_time >= today_start)
    )
    total_today = total_result.scalar_one()

    # Active now
    active_result = await db.execute(
        select(func.count(Visit.visit_id))
        .where(Visit.departure_time.is_(None))
    )
    active_now = active_result.scalar_one()

    # Average duration (completed visits today)
    avg_result = await db.execute(
        select(func.avg(
            func.timestampdiff(
                func.text('MINUTE'),
                Visit.arrival_time,
                Visit.departure_time
            )
        )).where(
            and_(
                Visit.arrival_time >= today_start,
                Visit.departure_time.isnot(None)
            )
        )
    )
    avg_duration = avg_result.scalar_one() or 0

    # New vs returning visitors today
    new_result = await db.execute(
        select(func.count(Visitor.visitor_id))
        .where(Visitor.created_at >= today_start)
    )
    new_visitors = new_result.scalar_one()

    returning_visitors = max(0, total_today - new_visitors)

    return VisitStatsResponse(
        total_today=total_today,
        active_now=active_now,
        average_duration_minutes=float(avg_duration),
        peak_hour=None,  # Would require GROUP BY hour query
        new_visitors_today=new_visitors,
        returning_visitors_today=returning_visitors,
    )


# ============================================================
# DEPARTURE DETECTION SERVICE
# ============================================================

class DepartureDetector:
    """
    Background service that detects when visitors have departed.
    
    Logic:
    - If no person detected for departure_timeout_seconds → visitor left
    - End their conversation session
    - Mark visit as departed
    - Save conversation to database
    - Broadcast dashboard update
    """

    def __init__(self):
        self.departure_timeout = settings.departure_timeout_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, app) -> None:
        """Start the departure detection background task."""
        self._running = True
        self._task = asyncio.create_task(self._detection_loop(app))
        logger.info("Departure detector started", timeout_seconds=self.departure_timeout)

    async def stop(self) -> None:
        """Stop the departure detection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Departure detector stopped")

    async def _detection_loop(self, app) -> None:
        """
        Periodically check for sessions that should be ended
        due to no activity (visitor departed).
        """
        while self._running:
            try:
                await self._check_timeouts(app)
            except Exception as e:
                logger.error("Departure detection error", error=str(e))

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _check_timeouts(self, app) -> None:
        """Check all active sessions for timeout."""
        if not hasattr(app.state, 'conversation_manager'):
            return

        conv_manager = app.state.conversation_manager
        now = datetime.utcnow()
        session_timeout = timedelta(seconds=settings.session_timeout_seconds)

        sessions_to_end = []

        for session_id, session in conv_manager.get_all_sessions().items():
            # Check if session has timed out (no activity)
            if now - session.last_activity > session_timeout:
                sessions_to_end.append(session_id)

        for session_id in sessions_to_end:
            session = conv_manager.get_session(session_id)
            if session:
                logger.info(
                    "Session timed out (visitor departed)",
                    session_id=session_id,
                    visitor_name=session.visitor_context.name,
                    inactive_seconds=(now - session.last_activity).total_seconds()
                )

                # End the session
                summary = await conv_manager.end_session(session_id)

                # End the visit record if exists
                if session.visit_id:
                    try:
                        async with AsyncSessionLocal() as db:
                            visit_repo = VisitRepository(db)
                            await visit_repo.end_visit(session.visit_id)

                            # Save conversation to database
                            if session.messages:
                                conv_repo = ConversationRepository(db)
                                conv = await conv_repo.create(
                                    session_id=session_id,
                                    visitor_id=session.visitor_id
                                )
                                for msg in session.messages:
                                    if msg.get("role") != "system":
                                        await conv_repo.add_message(
                                            conversation_id=conv.conversation_id,
                                            role=msg["role"],
                                            content=msg["content"]
                                        )
                                await conv_repo.end_conversation(
                                    conversation_id=conv.conversation_id,
                                    summary=f"Conversation with {session.visitor_context.name or 'visitor'}",
                                    message_count=session.message_count
                                )

                            await db.commit()
                    except Exception as e:
                        logger.error("Failed to end visit on timeout", error=str(e))

                # Broadcast to dashboard
                from api.websocket import ws_manager
                await ws_manager.broadcast_to_dashboards({
                    "type": "session_ended",
                    "session_id": session_id,
                    "reason": "timeout",
                    "summary": summary
                })


# Global instance
departure_detector = DepartureDetector()
