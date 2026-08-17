"""
Security Headers Middleware.
Adds enterprise security headers to all HTTP responses.

Headers applied:
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options (clickjacking protection)
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- Cache-Control for sensitive responses
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

from config import settings

logger = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies security headers to every HTTP response.
    Configurable via settings.enable_security_headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if not settings.enable_security_headers:
            return response

        # === HSTS: Force HTTPS in production ===
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.hsts_max_age}; includeSubDomains; preload"
            )

        # === Content-Security-Policy ===
        # Allow self for scripts/styles, inline for Tailwind/React, blob for audio playback
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # React needs eval in dev
            "style-src 'self' 'unsafe-inline'",  # Tailwind inline styles
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self' ws: wss: http: https:",  # WebSocket + API
            "media-src 'self' blob:",  # Audio playback from blobs
            "worker-src 'self' blob:",
            "frame-ancestors 'none'",  # Clickjacking protection via CSP
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # === X-Content-Type-Options: Prevent MIME sniffing ===
        response.headers["X-Content-Type-Options"] = "nosniff"

        # === X-Frame-Options: Clickjacking protection (legacy) ===
        response.headers["X-Frame-Options"] = "DENY"

        # === X-XSS-Protection: Legacy XSS filter ===
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # === Referrer-Policy: Limit referrer information ===
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # === Permissions-Policy: Restrict browser features ===
        permissions = [
            "camera=(self)",       # Allow camera for kiosk
            "microphone=(self)",   # Allow microphone for STT
            "geolocation=()",      # Deny geolocation
            "payment=()",          # Deny payment APIs
            "usb=()",              # Deny USB
            "autoplay=(self)",     # Allow autoplay for TTS
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions)

        # === Cache-Control for API responses ===
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response
