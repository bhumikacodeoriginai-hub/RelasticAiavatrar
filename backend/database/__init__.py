"""
Database package.
Provides database connection, models, and repository classes.
"""

from database.database import Base, get_db, init_db, close_db, AsyncSessionLocal, check_db_health
from database.models import (
    Visitor, Employee, Visit, Appointment,
    Conversation, ConversationMessage, Notification, AuditLog,
    ConsentStatus, VisitStatus, EmployeeAvailability, AppointmentStatus
)
from database.repositories import (
    VisitorRepository, EmployeeRepository, VisitRepository,
    AppointmentRepository, ConversationRepository, NotificationRepository
)
