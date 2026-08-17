"""
Session Store — Redis-backed conversation session storage.

Stores serializable session data in Redis with TTL for:
- Persistence across backend restarts
- Multi-instance session sharing
- Automatic expiry of abandoned sessions

Non-serializable data (numpy arrays like face embeddings) are kept
in a local in-memory cache and are ephemeral.

Graceful degradation: Falls back to pure in-memory if Redis unavailable.
"""

import json
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import asdict

import structlog

from config import settings
from services.redis_manager import redis_manager

logger = structlog.get_logger()

# Redis key prefix for conversation sessions
SESSION_PREFIX = "convsession:"
SESSION_TTL = settings.session_timeout_seconds + 60  # Extra buffer beyond timeout


class SessionStore:
    """
    Hybrid session store: Redis (primary) + in-memory (fallback/cache).
    
    All serializable session data goes to Redis.
    Local dict keeps a fast cache and stores non-serializable objects.
    """

    def __init__(self):
        # Local cache (always available, even without Redis)
        self._local: Dict[str, dict] = {}
        # Non-serializable data (numpy arrays, etc.) — keyed by session_id
        self._local_ephemeral: Dict[str, dict] = {}

    async def save(self, session_id: str, session_data: dict) -> None:
        """
        Save session data to Redis + local cache.
        
        Args:
            session_id: Unique session identifier
            session_data: Dict of serializable session fields
        """
        # Remove non-serializable fields before Redis storage
        redis_data = self._make_serializable(session_data)

        # Save to local cache (always)
        self._local[session_id] = session_data.copy()

        # Save to Redis (if available)
        success = await redis_manager.set(
            f"{SESSION_PREFIX}{session_id}",
            redis_data,
            ttl=SESSION_TTL
        )
        if not success:
            logger.debug("Session saved to local cache only (Redis unavailable)", session_id=session_id)

    async def get(self, session_id: str) -> Optional[dict]:
        """
        Get session data. Tries local cache first, then Redis.
        
        Returns:
            Session dict or None if not found
        """
        # Check local cache first (fast path)
        if session_id in self._local:
            return self._local[session_id]

        # Try Redis (for sessions from other instances or after restart)
        redis_data = await redis_manager.get(f"{SESSION_PREFIX}{session_id}")
        if redis_data:
            # Restore to local cache
            self._local[session_id] = redis_data
            return redis_data

        return None

    async def delete(self, session_id: str) -> None:
        """Remove a session from both stores."""
        self._local.pop(session_id, None)
        self._local_ephemeral.pop(session_id, None)
        await redis_manager.delete(f"{SESSION_PREFIX}{session_id}")

    async def extend_ttl(self, session_id: str) -> None:
        """Extend session TTL on activity."""
        await redis_manager.expire(f"{SESSION_PREFIX}{session_id}", SESSION_TTL)

    async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        if session_id in self._local:
            return True
        return await redis_manager.exists(f"{SESSION_PREFIX}{session_id}")

    def get_all_local(self) -> Dict[str, dict]:
        """Get all locally cached sessions (for departure detection)."""
        return self._local.copy()

    def local_count(self) -> int:
        """Count of sessions in local cache."""
        return len(self._local)

    # === Ephemeral (non-serializable) data ===

    def set_ephemeral(self, session_id: str, key: str, value: Any) -> None:
        """Store non-serializable data (e.g., numpy arrays) in local memory only."""
        if session_id not in self._local_ephemeral:
            self._local_ephemeral[session_id] = {}
        self._local_ephemeral[session_id][key] = value

    def get_ephemeral(self, session_id: str, key: str) -> Optional[Any]:
        """Get non-serializable data from local memory."""
        return self._local_ephemeral.get(session_id, {}).get(key)

    def clear_ephemeral(self, session_id: str) -> None:
        """Clear all ephemeral data for a session."""
        self._local_ephemeral.pop(session_id, None)

    # === Helpers ===

    @staticmethod
    def _make_serializable(data: dict) -> dict:
        """Remove non-JSON-serializable fields from session data."""
        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = None
            elif isinstance(value, (str, int, float, bool)):
                result[key] = value
            elif isinstance(value, (list, dict)):
                try:
                    json.dumps(value)
                    result[key] = value
                except (TypeError, ValueError):
                    pass  # Skip non-serializable
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            # Skip numpy arrays, objects, etc.
        return result


# Global singleton
session_store = SessionStore()
