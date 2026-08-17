"""
Rate Limiting Middleware.
Protects against brute force, DoS, and abuse.

Two layers:
1. Global API rate limit per IP (configurable requests/minute)
2. Login-specific rate limit (stricter, per IP)

Implementation:
- In-memory sliding window (suitable for single-instance)
- Designed for Redis upgrade in Phase 5 (multi-instance support)

Rate limit headers returned:
- X-RateLimit-Limit
- X-RateLimit-Remaining
- X-RateLimit-Reset
- Retry-After (on 429)
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
import structlog

from config import settings

logger = structlog.get_logger()


class SlidingWindowCounter:
    """
    Thread-safe in-memory sliding window rate counter.
    Tracks request counts per key within a time window.
    
    TODO: Replace with Redis ZADD-based sliding window in Phase 5
    for multi-instance deployments.
    """

    def __init__(self):
        self._lock = Lock()
        # key -> list of timestamps
        self._requests: Dict[str, list] = defaultdict(list)
        # Periodic cleanup counter
        self._cleanup_counter = 0

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        """
        Check if a key has exceeded its rate limit.
        
        Args:
            key: Rate limit key (e.g., IP address)
            max_requests: Maximum allowed requests in the window
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (is_limited, remaining_requests, reset_timestamp)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Remove expired entries
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > window_start
            ]

            current_count = len(self._requests[key])

            if current_count >= max_requests:
                # Rate limited
                oldest = self._requests[key][0] if self._requests[key] else now
                reset_time = int(oldest + window_seconds)
                return True, 0, reset_time

            # Record this request
            self._requests[key].append(now)
            remaining = max_requests - current_count - 1
            reset_time = int(now + window_seconds)

            # Periodic cleanup of stale keys (every 100 checks)
            self._cleanup_counter += 1
            if self._cleanup_counter >= 100:
                self._cleanup_counter = 0
                self._cleanup(window_start)

            return False, remaining, reset_time

    def _cleanup(self, window_start: float) -> None:
        """Remove keys with no recent requests."""
        stale_keys = [
            key for key, timestamps in self._requests.items()
            if not timestamps or all(ts <= window_start for ts in timestamps)
        ]
        for key in stale_keys:
            del self._requests[key]

    def get_count(self, key: str, window_seconds: int) -> int:
        """Get current count for a key without incrementing."""
        now = time.time()
        window_start = now - window_seconds
        with self._lock:
            return len([ts for ts in self._requests.get(key, []) if ts > window_start])


# Global rate limiter instances
_api_limiter = SlidingWindowCounter()
_login_limiter = SlidingWindowCounter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with two policies:
    1. Login endpoint: Strict limit (login_max_attempts per lockout window)
    2. General API: Broader limit (api_rate_limit_per_minute)
    
    Exempt paths: /health, /docs, /redoc, /openapi.json, static assets
    """

    # Paths exempt from rate limiting
    EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for exempt paths and non-API routes
        path = request.url.path
        if path in self.EXEMPT_PATHS or not path.startswith("/api/"):
            return await call_next(request)

        # Get client IP (support X-Forwarded-For for proxied requests)
        client_ip = self._get_client_ip(request)

        # === Login-specific rate limiting (stricter) ===
        if path == "/api/auth/login" and request.method == "POST":
            is_limited, remaining, reset_time = _login_limiter.is_rate_limited(
                key=f"login:{client_ip}",
                max_requests=settings.login_max_attempts * 2,  # Allow some above account lockout
                window_seconds=settings.login_lockout_seconds,
            )

            if is_limited:
                retry_after = max(1, reset_time - int(time.time()))
                logger.warning(
                    "Login rate limit exceeded",
                    ip=client_ip,
                    retry_after=retry_after,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many login attempts. Retry after {retry_after} seconds.",
                        "retry_after": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(settings.login_max_attempts * 2),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                    },
                )

        # === General API rate limiting ===
        is_limited, remaining, reset_time = _api_limiter.is_rate_limited(
            key=f"api:{client_ip}",
            max_requests=settings.api_rate_limit_per_minute,
            window_seconds=60,
        )

        if is_limited:
            retry_after = max(1, reset_time - int(time.time()))
            logger.warning(
                "API rate limit exceeded",
                ip=client_ip,
                path=path,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(settings.api_rate_limit_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        # Add rate limit headers to successful responses
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.api_rate_limit_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For from trusted proxies."""
        # In production behind ALB/CloudFront, use X-Forwarded-For
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in the chain is the original client
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
