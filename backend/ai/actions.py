"""
AI Actions Service.
Implements controlled backend actions that the conversation can trigger.
Llama can REQUEST actions, but the backend VALIDATES and EXECUTES them.
Llama never directly executes SQL or accesses databases.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import structlog

from database.database import AsyncSessionLocal
from database.repositories import (
    VisitorRepository, EmployeeRepository, AppointmentRepository,
    VisitRepository, NotificationRepository
)

logger = structlog.get_logger()


class AIActionsService:
    """
    Service layer for AI-triggered actions.
    All database operations go through repositories.
    
    Available actions:
    - find_employee: Search for an employee by name
    - check_employee_availability: Check if an employee is available
    - notify_employee: Send notification to an employee
    - find_appointment: Look up appointments for a visitor
    - create_appointment_request: Request a new appointment
    - create_visit: Create a visit record
    - end_visit: End a visit (mark departed)
    """

    @staticmethod
    async def find_employee(name: str) -> Dict[str, Any]:
        """
        Find an employee by name.
        Returns employee info or not-found status.
        """
        try:
            async with AsyncSessionLocal() as db:
                repo = EmployeeRepository(db)
                employees = await repo.search_by_name(name)

                if employees:
                    emp = employees[0]
                    return {
                        "found": True,
                        "employee_id": emp.employee_id,
                        "name": emp.name,
                        "email": emp.email,
                        "department": emp.department,
                        "designation": emp.designation,
                        "office_location": emp.office_location,
                        "availability": emp.availability,
                    }
                else:
                    return {
                        "found": False,
                        "message": f"No employee found matching '{name}'"
                    }
        except Exception as e:
            logger.error("find_employee action failed", error=str(e))
            return {"found": False, "error": str(e)}

    @staticmethod
    async def check_employee_availability(employee_id: str) -> Dict[str, Any]:
        """Check an employee's current availability."""
        try:
            async with AsyncSessionLocal() as db:
                repo = EmployeeRepository(db)
                employee = await repo.get_by_id(employee_id)

                if employee:
                    return {
                        "found": True,
                        "name": employee.name,
                        "availability": employee.availability,
                        "office_location": employee.office_location,
                    }
                else:
                    return {"found": False, "message": "Employee not found"}
        except Exception as e:
            logger.error("check_availability action failed", error=str(e))
            return {"found": False, "error": str(e)}

    @staticmethod
    async def notify_employee(
        employee_id: str,
        visitor_name: str,
        visitor_id: Optional[str] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a notification to an employee that a visitor has arrived.
        """
        try:
            async with AsyncSessionLocal() as db:
                repo = NotificationRepository(db)
                notification_message = message or (
                    f"Visitor {visitor_name} has arrived and would like to see you."
                )
                notification = await repo.create(
                    employee_id=employee_id,
                    message=notification_message,
                    notification_type="visitor_arrived",
                    visitor_id=visitor_id,
                )
                await db.commit()

                logger.info(
                    "Employee notified",
                    employee_id=employee_id,
                    visitor_name=visitor_name
                )

                return {
                    "success": True,
                    "notification_id": notification.notification_id,
                    "message": f"Notification sent to employee"
                }
        except Exception as e:
            logger.error("notify_employee action failed", error=str(e))
            return {"success": False, "error": str(e)}

    @staticmethod
    async def find_appointment(
        visitor_id: str,
        employee_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find today's appointments for a visitor."""
        try:
            async with AsyncSessionLocal() as db:
                repo = AppointmentRepository(db)
                appointments = await repo.find_for_visitor_today(
                    visitor_id=visitor_id,
                    employee_id=employee_id
                )

                if appointments:
                    appt = appointments[0]
                    return {
                        "found": True,
                        "appointment_id": appt.appointment_id,
                        "appointment_time": appt.appointment_time.isoformat(),
                        "purpose": appt.purpose,
                        "status": appt.status,
                    }
                else:
                    return {
                        "found": False,
                        "message": "No appointments found for today"
                    }
        except Exception as e:
            logger.error("find_appointment action failed", error=str(e))
            return {"found": False, "error": str(e)}

    @staticmethod
    async def create_visit(
        visitor_id: str,
        employee_id: Optional[str] = None,
        purpose: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new visit record."""
        try:
            async with AsyncSessionLocal() as db:
                repo = VisitRepository(db)
                visit = await repo.create(
                    visitor_id=visitor_id,
                    employee_id=employee_id,
                    purpose=purpose,
                    conversation_id=conversation_id,
                )
                await db.commit()

                return {
                    "success": True,
                    "visit_id": visit.visit_id,
                    "status": visit.status,
                }
        except Exception as e:
            logger.error("create_visit action failed", error=str(e))
            return {"success": False, "error": str(e)}

    @staticmethod
    async def end_visit(visit_id: str) -> Dict[str, Any]:
        """End a visit (mark as departed)."""
        try:
            async with AsyncSessionLocal() as db:
                repo = VisitRepository(db)
                await repo.end_visit(visit_id)
                await db.commit()

                return {
                    "success": True,
                    "message": "Visit marked as departed"
                }
        except Exception as e:
            logger.error("end_visit action failed", error=str(e))
            return {"success": False, "error": str(e)}

    @staticmethod
    async def create_appointment_request(
        visitor_id: str,
        employee_id: str,
        purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an appointment request (defaults to now)."""
        try:
            async with AsyncSessionLocal() as db:
                repo = AppointmentRepository(db)
                appointment = await repo.create(
                    employee_id=employee_id,
                    appointment_time=datetime.utcnow(),
                    visitor_id=visitor_id,
                    purpose=purpose,
                )
                await db.commit()

                return {
                    "success": True,
                    "appointment_id": appointment.appointment_id,
                    "status": appointment.status,
                }
        except Exception as e:
            logger.error("create_appointment_request action failed", error=str(e))
            return {"success": False, "error": str(e)}

    @staticmethod
    async def update_visitor_last_seen(visitor_id: str) -> Dict[str, Any]:
        """Update visitor's last_seen timestamp."""
        try:
            async with AsyncSessionLocal() as db:
                repo = VisitorRepository(db)
                await repo.update_last_seen(visitor_id)
                await db.commit()
                return {"success": True}
        except Exception as e:
            logger.error("update_visitor_last_seen failed", error=str(e))
            return {"success": False, "error": str(e)}
