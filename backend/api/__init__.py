"""
API routes for the AI Avatar Receptionist.
"""

from api.auth import router as auth_router
from api.visitor import router as visitor_router
from api.conversation import router as conversation_router
from api.employee import router as employee_router
from api.websocket import router as websocket_router
from api.dashboard import router as dashboard_router
from api.visits import router as visits_router

__all__ = [
    "auth_router",
    "visitor_router",
    "conversation_router",
    "employee_router",
    "websocket_router",
    "dashboard_router",
    "visits_router",
]
