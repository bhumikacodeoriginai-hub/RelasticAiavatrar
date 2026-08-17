"""
Employee API endpoints.
Handles employee directory and availability management.
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.database import get_db
from database.repositories import EmployeeRepository, NotificationRepository

logger = structlog.get_logger()

router = APIRouter(prefix="/api/employees", tags=["employees"])


# === Pydantic Schemas ===

class EmployeeCreate(BaseModel):
    """Schema for creating an employee."""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    office_location: Optional[str] = None
    availability: str = Field(default="available")


class EmployeeResponse(BaseModel):
    """Schema for employee response."""
    employee_id: str
    name: str
    email: str
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    office_location: Optional[str] = None
    availability: str

    class Config:
        from_attributes = True


class AvailabilityUpdate(BaseModel):
    """Schema for updating availability."""
    availability: str = Field(..., pattern="^(available|busy|away|offline)$")


# === Endpoints ===

@router.get("/", response_model=List[EmployeeResponse])
async def list_employees(
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all employees, optionally filtered by department."""
    repo = EmployeeRepository(db)
    employees = await repo.get_all(department=department)

    return [
        EmployeeResponse(
            employee_id=e.employee_id,
            name=e.name,
            email=e.email,
            phone=e.phone,
            department=e.department,
            designation=e.designation,
            office_location=e.office_location,
            availability=e.availability
        )
        for e in employees
    ]


@router.get("/search/{name}", response_model=List[EmployeeResponse])
async def search_employee(
    name: str,
    db: AsyncSession = Depends(get_db)
):
    """Search for employees by name (partial match)."""
    repo = EmployeeRepository(db)
    employees = await repo.search_by_name(name)

    return [
        EmployeeResponse(
            employee_id=e.employee_id,
            name=e.name,
            email=e.email,
            phone=e.phone,
            department=e.department,
            designation=e.designation,
            office_location=e.office_location,
            availability=e.availability
        )
        for e in employees
    ]


@router.get("/available/list", response_model=List[EmployeeResponse])
async def list_available_employees(db: AsyncSession = Depends(get_db)):
    """List all currently available employees."""
    repo = EmployeeRepository(db)
    employees = await repo.get_available()

    return [
        EmployeeResponse(
            employee_id=e.employee_id,
            name=e.name,
            email=e.email,
            phone=e.phone,
            department=e.department,
            designation=e.designation,
            office_location=e.office_location,
            availability=e.availability
        )
        for e in employees
    ]


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific employee by ID."""
    repo = EmployeeRepository(db)
    employee = await repo.get_by_id(employee_id)

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return EmployeeResponse(
        employee_id=employee.employee_id,
        name=employee.name,
        email=employee.email,
        phone=employee.phone,
        department=employee.department,
        designation=employee.designation,
        office_location=employee.office_location,
        availability=employee.availability
    )


@router.post("/", response_model=EmployeeResponse)
async def create_employee(
    employee: EmployeeCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new employee record."""
    repo = EmployeeRepository(db)
    new_employee = await repo.create(
        name=employee.name,
        email=employee.email,
        phone=employee.phone,
        department=employee.department,
        designation=employee.designation,
        office_location=employee.office_location,
    )

    if employee.availability != "available":
        await repo.update_availability(new_employee.employee_id, employee.availability)

    await db.commit()
    logger.info("Employee created", employee_id=new_employee.employee_id)

    return EmployeeResponse(
        employee_id=new_employee.employee_id,
        name=new_employee.name,
        email=new_employee.email,
        phone=new_employee.phone,
        department=new_employee.department,
        designation=new_employee.designation,
        office_location=new_employee.office_location,
        availability=new_employee.availability
    )


@router.put("/{employee_id}/availability")
async def update_availability(
    employee_id: str,
    avail: AvailabilityUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an employee's availability status."""
    repo = EmployeeRepository(db)
    success = await repo.update_availability(employee_id, avail.availability)

    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")

    await db.commit()
    return {"message": f"Availability updated to: {avail.availability}"}
