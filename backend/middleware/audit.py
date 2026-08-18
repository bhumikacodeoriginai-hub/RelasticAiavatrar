"""
Audit Logging Middleware.
Logs security-sensitive operations to the audit_logs table.

What is logged:
- All POST/PUT/DELETE API requests (state-changing operations)
- The user who performed the action (from JWT)
- Client IP address
- Request path and method
- Response status code

What is NOT logged:
- GET requests (read-only)
- Request/response bodies (may contain sensitive data)
- Raw images, audio, or embeddings
- Internal health checks
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

from config import settings

logger = structlog.get_logger()

# Paths exempt from audit logging
EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

# Methods that trigger audit logging (state-changing only)
AUDITED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Logs state-changing API operations for audit trail.
    Writes structured log entries (these can be shipped to CloudWatch/SIEM).
    Database audit entries are written by individual endpoint handlers for
    richer context (entity_type, entity_id, details).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip OPTIONS preflight requests (handled by CORS middleware)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip non-API and read-only requests
        path = request.url.path
        method = request.method

        if path in EXEMPT_PATHS or not path.startswith("/api/") or method not in AUDITED_METHODS:
            return await call_next(request)

        # Extract user info from token (if present)
        user_info = self._extract_user_from_auth_header(request)
        client_ip = self._get_client_ip(request)

        # Time the request
        start_time = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)

        # Log the audit event
        log_data = {
            "event": "api_audit",
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
            "user_id": user_info.get("user_id") if user_info else None,
            "username": user_info.get("username") if user_info else None,
            "role": user_info.get("role") if user_info else None,
        }

        if response.status_code >= 400:
            logger.warning("Audit: failed operation", **log_data)
        else:
            logger.info("Audit: successful operation", **log_data)

        return response

    @staticmethod
    def _extract_user_from_auth_header(request: Request) -> dict | None:
        """Extract user claims from Authorization header without DB lookup."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        try:
            from api.auth import verify_token
            payload = verify_token(token)
            if payload:
                return {
                    "user_id": payload.get("sub"),
                    "username": payload.get("username"),
                    "role": payload.get("role"),
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
