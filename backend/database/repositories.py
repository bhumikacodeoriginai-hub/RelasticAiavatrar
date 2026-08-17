"""
Repository layer for all database operations.
All database access must go through these services.
No raw SQL in API handlers or other modules.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

import numpy as np
from sqlalchemy import select, update, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.models import (
    Visitor, Employee, Visit, Appointment,
    Conversation, ConversationMessage, Notification, AuditLog,
    ConsentStatus, VisitStatus, AppointmentStatus
)

logger = structlog.get_logger()


# ============================================================
# VISITOR REPOSITORY
# ============================================================

class VisitorRepository:
    """Repository for visitor database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        face_embedding: Optional[np.ndarray] = None,
        profile_image_path: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        role: Optional[str] = None,
        consent_status: str = ConsentStatus.PENDING.value
    ) -> Visitor:
        """Create a new visitor record."""
        visitor = Visitor(
            visitor_id=str(uuid.uuid4()),
            name=name,
            email=email,
            phone=phone,
            company=company,
            role=role,
            profile_image_path=profile_image_path,
            face_embedding=face_embedding.tolist() if face_embedding is not None else None,
            consent_status=consent_status,
            consent_timestamp=datetime.utcnow() if consent_status == ConsentStatus.GRANTED.value else None,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            visit_count=1
        )
        self.db.add(visitor)
        await self.db.flush()
        logger.info("Created new visitor", visitor_id=visitor.visitor_id, name=name)
        return visitor

    async def get_by_id(self, visitor_id: str) -> Optional[Visitor]:
        """Get a visitor by their ID."""
        result = await self.db.execute(
            select(Visitor).where(Visitor.visitor_id == visitor_id)
        )
        return result.scalar_one_or_none()

    async def search_by_face(
        self,
        embedding: np.ndarray,
        threshold: float = 0.6,
        limit: int = 5
    ) -> List[Tuple[Visitor, float]]:
        """
        Search for a visitor by face embedding using cosine similarity.
        In MySQL, we load all consented embeddings and compute similarity in Python.
        Returns list of (visitor, similarity_score) tuples sorted by similarity desc.
        """
        # Fetch all visitors with face embeddings who have granted consent
        result = await self.db.execute(
            select(Visitor)
            .where(
                and_(
                    Visitor.face_embedding.isnot(None),
                    Visitor.consent_status == ConsentStatus.GRANTED.value
                )
            )
        )
        visitors = result.scalars().all()

        if not visitors:
            return []

        # Normalize query embedding
        query_norm = embedding / (np.linalg.norm(embedding) + 1e-10)

        matches = []
        for visitor in visitors:
            stored_embedding = np.array(visitor.face_embedding, dtype=np.float32)
            stored_norm = stored_embedding / (np.linalg.norm(stored_embedding) + 1e-10)

            # Cosine similarity
            similarity = float(np.dot(query_norm, stored_norm))

            if similarity >= threshold:
                matches.append((visitor, similarity))

        # Sort by similarity descending
        matches.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "Face search completed",
            total_candidates=len(visitors),
            matches_found=len(matches[:limit]),
            threshold=threshold
        )
        return matches[:limit]

    async def update_last_seen(self, visitor_id: str) -> None:
        """Update the last_seen timestamp and increment visit count."""
        await self.db.execute(
            update(Visitor)
            .where(Visitor.visitor_id == visitor_id)
            .values(
                last_seen=datetime.utcnow(),
                visit_count=Visitor.visit_count + 1
            )
        )

    async def update_consent(
        self,
        visitor_id: str,
        consent_status: str,
        face_embedding: Optional[np.ndarray] = None
    ) -> None:
        """Update consent status. If granting, optionally store embedding."""
        values = {
            "consent_status": consent_status,
            "consent_timestamp": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        if consent_status == ConsentStatus.GRANTED.value and face_embedding is not None:
            values["face_embedding"] = face_embedding.tolist()
        elif consent_status == ConsentStatus.REVOKED.value:
            # GDPR: remove biometric data on revocation
            values["face_embedding"] = None
            values["profile_image_path"] = None

        await self.db.execute(
            update(Visitor)
            .where(Visitor.visitor_id == visitor_id)
            .values(**values)
        )
        logger.info("Updated consent", visitor_id=visitor_id, status=consent_status)

    async def revoke_consent(self, visitor_id: str) -> None:
        """Revoke consent and remove biometric data (GDPR compliance)."""
        await self.update_consent(visitor_id, ConsentStatus.REVOKED.value)

    async def delete(self, visitor_id: str) -> bool:
        """Delete a visitor and all associated data (GDPR compliance)."""
        visitor = await self.get_by_id(visitor_id)
        if visitor:
            await self.db.delete(visitor)
            logger.info("Deleted visitor", visitor_id=visitor_id)
            return True
        return False

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Visitor]:
        """Get all visitors with pagination."""
        result = await self.db.execute(
            select(Visitor)
            .order_by(Visitor.last_seen.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        """Get visitor statistics."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        total_today = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.arrival_time >= today_start)
        )
        active = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.departure_time.is_(None), Visit.status == VisitStatus.ARRIVED.value)
        )
        total_visitors = await self.db.execute(
            select(func.count(Visitor.visitor_id))
        )

        return {
            "visits_today": total_today.scalar_one(),
            "active_visitors": active.scalar_one(),
            "total_registered": total_visitors.scalar_one()
        }


# ============================================================
# EMPLOYEE REPOSITORY
# ============================================================

class EmployeeRepository:
    """Repository for employee database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        email: str,
        phone: Optional[str] = None,
        department: Optional[str] = None,
        designation: Optional[str] = None,
        office_location: Optional[str] = None,
    ) -> Employee:
        """Create a new employee record."""
        employee = Employee(
            employee_id=str(uuid.uuid4()),
            name=name,
            email=email,
            phone=phone,
            department=department,
            designation=designation,
            office_location=office_location,
        )
        self.db.add(employee)
        await self.db.flush()
        logger.info("Created employee", employee_id=employee.employee_id, name=name)
        return employee

    async def get_by_id(self, employee_id: str) -> Optional[Employee]:
        """Get an employee by their ID."""
        result = await self.db.execute(
            select(Employee).where(Employee.employee_id == employee_id)
        )
        return result.scalar_one_or_none()

    async def search_by_name(self, name: str) -> List[Employee]:
        """Search for employees by name (case-insensitive partial match)."""
        # Escape SQL wildcards in user input
        safe_name = name.replace("%", "\\%").replace("_", "\\_")
        result = await self.db.execute(
            select(Employee)
            .where(Employee.name.ilike(f"%{safe_name}%"))
            .order_by(Employee.name)
        )
        return list(result.scalars().all())

    async def get_all(self, department: Optional[str] = None) -> List[Employee]:
        """Get all employees, optionally filtered by department."""
        query = select(Employee)
        if department:
            query = query.where(Employee.department == department)
        query = query.order_by(Employee.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_available(self) -> List[Employee]:
        """Get all currently available employees."""
        result = await self.db.execute(
            select(Employee)
            .where(Employee.availability == "available")
            .order_by(Employee.name)
        )
        return list(result.scalars().all())

    async def update_availability(self, employee_id: str, availability: str) -> bool:
        """Update an employee's availability status."""
        result = await self.db.execute(
            update(Employee)
            .where(Employee.employee_id == employee_id)
            .values(availability=availability, updated_at=datetime.utcnow())
        )
        return result.rowcount > 0

    async def check_availability(self, employee_id: str) -> Optional[str]:
        """Check an employee's current availability."""
        employee = await self.get_by_id(employee_id)
        return employee.availability if employee else None

    async def count(self) -> int:
        """Get total employee count."""
        result = await self.db.execute(
            select(func.count(Employee.employee_id))
        )
        return result.scalar_one()


# ============================================================
# VISIT REPOSITORY
# ============================================================

class VisitRepository:
    """Repository for visit tracking operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        visitor_id: str,
        employee_id: Optional[str] = None,
        purpose: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Visit:
        """Create a new visit record."""
        visit = Visit(
            visit_id=str(uuid.uuid4()),
            visitor_id=visitor_id,
            employee_id=employee_id,
            purpose=purpose,
            conversation_id=conversation_id,
        )
        self.db.add(visit)
        await self.db.flush()
        logger.info("Created visit", visit_id=visit.visit_id, visitor_id=visitor_id)
        return visit

    async def end_visit(self, visit_id: str) -> None:
        """Mark a visit as departed."""
        await self.db.execute(
            update(Visit)
            .where(Visit.visit_id == visit_id)
            .values(
                departure_time=datetime.utcnow(),
                status=VisitStatus.DEPARTED.value
            )
        )

    async def get_active_visits(self) -> List[Visit]:
        """Get all currently active visits (not departed)."""
        result = await self.db.execute(
            select(Visit)
            .where(Visit.departure_time.is_(None))
            .order_by(Visit.arrival_time.desc())
        )
        return list(result.scalars().all())

    async def get_active_visit_for_visitor(self, visitor_id: str) -> Optional[Visit]:
        """Get the current active visit for a visitor (if any)."""
        result = await self.db.execute(
            select(Visit)
            .where(
                and_(
                    Visit.visitor_id == visitor_id,
                    Visit.departure_time.is_(None)
                )
            )
            .order_by(Visit.arrival_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_today_visits(self) -> List[Visit]:
        """Get all visits from today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(Visit)
            .where(Visit.arrival_time >= today_start)
            .order_by(Visit.arrival_time.desc())
        )
        return list(result.scalars().all())

    async def get_today_stats(self) -> dict:
        """Get today's visit statistics."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        total_today = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.arrival_time >= today_start)
        )
        active = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.departure_time.is_(None))
        )

        return {
            "total_today": total_today.scalar_one(),
            "active_now": active.scalar_one()
        }


# ============================================================
# APPOINTMENT REPOSITORY
# ============================================================

class AppointmentRepository:
    """Repository for appointment operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        employee_id: str,
        appointment_time: datetime,
        visitor_id: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> Appointment:
        """Create a new appointment."""
        appointment = Appointment(
            appointment_id=str(uuid.uuid4()),
            visitor_id=visitor_id,
            employee_id=employee_id,
            appointment_time=appointment_time,
            purpose=purpose,
        )
        self.db.add(appointment)
        await self.db.flush()
        logger.info("Created appointment", appointment_id=appointment.appointment_id)
        return appointment

    async def get_by_id(self, appointment_id: str) -> Optional[Appointment]:
        """Get an appointment by ID."""
        result = await self.db.execute(
            select(Appointment).where(Appointment.appointment_id == appointment_id)
        )
        return result.scalar_one_or_none()

    async def find_for_visitor_today(
        self,
        visitor_id: str,
        employee_id: Optional[str] = None
    ) -> List[Appointment]:
        """Find today's appointments for a visitor, optionally with a specific employee."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        query = select(Appointment).where(
            and_(
                Appointment.visitor_id == visitor_id,
                Appointment.appointment_time >= today_start,
                Appointment.appointment_time < today_end,
                Appointment.status.in_([
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value
                ])
            )
        )
        if employee_id:
            query = query.where(Appointment.employee_id == employee_id)

        result = await self.db.execute(query.order_by(Appointment.appointment_time))
        return list(result.scalars().all())

    async def update_status(self, appointment_id: str, status: str) -> None:
        """Update appointment status."""
        await self.db.execute(
            update(Appointment)
            .where(Appointment.appointment_id == appointment_id)
            .values(status=status, updated_at=datetime.utcnow())
        )

    async def get_upcoming_for_employee(self, employee_id: str) -> List[Appointment]:
        """Get upcoming appointments for an employee."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.employee_id == employee_id,
                    Appointment.appointment_time >= now,
                    Appointment.status.in_([
                        AppointmentStatus.SCHEDULED.value,
                        AppointmentStatus.CONFIRMED.value
                    ])
                )
            )
            .order_by(Appointment.appointment_time)
        )
        return list(result.scalars().all())


# ============================================================
# CONVERSATION REPOSITORY
# ============================================================

class ConversationRepository:
    """Repository for conversation persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        session_id: str,
        visitor_id: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation record."""
        conversation = Conversation(
            conversation_id=str(uuid.uuid4()),
            visitor_id=visitor_id,
            session_id=session_id,
        )
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def end_conversation(
        self,
        conversation_id: str,
        summary: Optional[str] = None,
        message_count: int = 0
    ) -> None:
        """Mark a conversation as ended."""
        await self.db.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(
                ended_at=datetime.utcnow(),
                summary=summary,
                message_count=message_count
            )
        )

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str
    ) -> ConversationMessage:
        """Add a message to a conversation."""
        message = ConversationMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.db.add(message)
        await self.db.flush()
        return message

    async def get_active_count(self) -> int:
        """Get count of active (not ended) conversations."""
        result = await self.db.execute(
            select(func.count(Conversation.conversation_id))
            .where(Conversation.ended_at.is_(None))
        )
        return result.scalar_one()

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        """Get conversation by session ID."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        return result.scalar_one_or_none()


# ============================================================
# NOTIFICATION REPOSITORY
# ============================================================

class NotificationRepository:
    """Repository for notification operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        employee_id: str,
        message: str,
        notification_type: str = "visitor_arrived",
        visitor_id: Optional[str] = None
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            notification_id=str(uuid.uuid4()),
            employee_id=employee_id,
            visitor_id=visitor_id,
            notification_type=notification_type,
            message=message,
        )
        self.db.add(notification)
        await self.db.flush()
        logger.info("Created notification", employee_id=employee_id, type=notification_type)
        return notification

    async def get_unread_for_employee(self, employee_id: str) -> List[Notification]:
        """Get unread notifications for an employee."""
        result = await self.db.execute(
            select(Notification)
            .where(
                and_(
                    Notification.employee_id == employee_id,
                    Notification.is_read == False
                )
            )
            .order_by(Notification.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_read(self, notification_id: str) -> None:
        """Mark a notification as read."""
        await self.db.execute(
            update(Notification)
            .where(Notification.notification_id == notification_id)
            .values(is_read=True)
        )
