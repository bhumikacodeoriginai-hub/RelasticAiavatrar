"""
SQLAlchemy ORM models for the AI Receptionist application.
Standardized on MySQL. Face embeddings stored as JSON (512-dim float arrays).
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Text, DateTime, JSON,
    ForeignKey, Boolean, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

from database.database import Base


# ============== Enums ==============

class ConsentStatus(str, enum.Enum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"


class VisitStatus(str, enum.Enum):
    ARRIVED = "arrived"
    IN_MEETING = "in_meeting"
    DEPARTED = "departed"
    CANCELLED = "cancelled"


class EmployeeAvailability(str, enum.Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class NotificationType(str, enum.Enum):
    VISITOR_ARRIVED = "visitor_arrived"
    APPOINTMENT_REMINDER = "appointment_reminder"
    VISITOR_WAITING = "visitor_waiting"
    SYSTEM = "system"


# ============== Models ==============

class Visitor(Base):
    """Stores all recognized visitors."""
    __tablename__ = "visitors"

    visitor_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    profile_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    face_embedding: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    consent_status: Mapped[str] = mapped_column(
        String(20), default=ConsentStatus.PENDING.value, nullable=False
    )
    consent_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    visits: Mapped[List["Visit"]] = relationship(
        back_populates="visitor", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="visitor"
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="visitor"
    )

    __table_args__ = (
        Index("idx_visitors_name", "name"),
        Index("idx_visitors_last_seen", "last_seen"),
        Index("idx_visitors_consent", "consent_status"),
    )


class Employee(Base):
    """Internal office employees."""
    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    office_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    availability: Mapped[str] = mapped_column(
        String(20), default=EmployeeAvailability.AVAILABLE.value, nullable=False
    )
    face_embedding: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="employee"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        back_populates="employee"
    )

    __table_args__ = (
        Index("idx_employees_name", "name"),
        Index("idx_employees_department", "department"),
        Index("idx_employees_availability", "availability"),
    )


class Visit(Base):
    """Tracks each physical visit instance."""
    __tablename__ = "visits"

    visit_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    visitor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("visitors.visitor_id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.employee_id"), nullable=True
    )
    arrival_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    departure_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=VisitStatus.ARRIVED.value, nullable=False
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    visitor: Mapped["Visitor"] = relationship(back_populates="visits")

    __table_args__ = (
        Index("idx_visits_visitor_id", "visitor_id"),
        Index("idx_visits_arrival", "arrival_time"),
        Index("idx_visits_status", "status"),
    )


class Appointment(Base):
    """Scheduled appointments between visitors and employees."""
    __tablename__ = "appointments"

    appointment_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    visitor_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("visitors.visitor_id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.employee_id"), nullable=False
    )
    appointment_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=AppointmentStatus.SCHEDULED.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    visitor: Mapped[Optional["Visitor"]] = relationship(back_populates="appointments")
    employee: Mapped["Employee"] = relationship(back_populates="appointments")

    __table_args__ = (
        Index("idx_appointments_visitor", "visitor_id"),
        Index("idx_appointments_employee", "employee_id"),
        Index("idx_appointments_time", "appointment_time"),
        Index("idx_appointments_status", "status"),
    )


class Conversation(Base):
    """Stores conversation sessions."""
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    visitor_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("visitors.visitor_id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    visitor: Mapped[Optional["Visitor"]] = relationship(back_populates="conversations")
    messages: Mapped[List["ConversationMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_conversations_visitor", "visitor_id"),
        Index("idx_conversations_session", "session_id"),
    )


class ConversationMessage(Base):
    """Individual messages in a conversation."""
    __tablename__ = "conversation_messages"

    message_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_messages_conversation", "conversation_id"),
    )


class Notification(Base):
    """Notifications sent to employees."""
    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.employee_id"), nullable=False
    )
    visitor_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("visitors.visitor_id", ondelete="SET NULL"), nullable=True
    )
    notification_type: Mapped[str] = mapped_column(
        String(30), default=NotificationType.VISITOR_ARRIVED.value, nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("idx_notifications_employee", "employee_id"),
        Index("idx_notifications_read", "is_read"),
    )


class AuditLog(Base):
    """Audit trail for sensitive operations."""
    __tablename__ = "audit_logs"

    log_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_audit_action", "action"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_created", "created_at"),
    )



# ============== Auth Models ==============

class UserRoleEnum(str, enum.Enum):
    """
    Enterprise RBAC roles (ordered by privilege level).
    Principle of least privilege — each role inherits nothing from others.
    """
    SUPER_ADMIN = "super_admin"
    IT_ADMIN = "it_admin"
    SECURITY_OFFICER = "security_officer"
    RECEPTION_MANAGER = "reception_manager"
    RECEPTIONIST = "receptionist"
    AUDITOR = "auditor"
    VIEWER = "viewer"
    KIOSK_DEVICE = "kiosk_device"


class Role(Base):
    """RBAC roles with permission sets."""
    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permissions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    users: Mapped[List["User"]] = relationship(back_populates="role")

    __table_args__ = (
        Index("idx_roles_name", "name"),
    )


class User(Base):
    """
    Application users (administrators, managers, devices).
    Passwords stored with bcrypt hash — NEVER plaintext.
    """
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.role_id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    role: Mapped["Role"] = relationship(back_populates="users")

    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role_id"),
        Index("idx_users_active", "is_active"),
    )
