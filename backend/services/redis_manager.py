"""
Redis Connection Manager.
Provides a shared Redis connection pool with health checks, TTL management,
and pub/sub support for multi-instance deployments.

Usage:
    from services.redis_manager import redis_manager
    await redis_manager.initialize()
    await redis_manager.set("key", "value", ttl=300)
    value = await redis_manager.get("key")
"""

import json
import asyncio
from typing import Optional, Any
from datetime import timedelta

import redis.asyncio as aioredis
import structlog

from config import settings

logger = structlog.get_logger()


class RedisManager:
    """
    Centralized Redis connection manager.
    Provides:
    - Connection pool with health monitoring
    - Key-value operations with JSON serialization
    - TTL management
    - Pub/Sub messaging
    - Rate limiting primitives
    - Graceful degradation when Redis is unavailable
    """

    def __init__(self):
        self._pool: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._initialized = False
        self._healthy = False

    async def initialize(self) -> None:
        """Initialize Redis connection pool."""
        try:
            self._pool = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True,
            )
            # Verify connection
            await self._pool.ping()
            self._initialized = True
            self._healthy = True
            logger.info("Redis initialized", url=settings.redis_url.split("@")[-1])
        except Exception as e:
            logger.error("Redis initialization failed — running without Redis", error=str(e))
            self._initialized = False
            self._healthy = False

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._pool:
            await self._pool.close()
            self._initialized = False
            self._healthy = False
            logger.info("Redis connection closed")

    async def health_check(self) -> bool:
        """Check if Redis is reachable."""
        if not self._pool:
            return False
        try:
            await self._pool.ping()
            self._healthy = True
            return True
        except Exception:
            self._healthy = False
            return False

    @property
    def is_available(self) -> bool:
        """Whether Redis is initialized and healthy."""
        return self._initialized and self._healthy

    # ============================================================
    # Key-Value Operations (JSON serialized)
    # ============================================================

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a key with optional TTL (seconds).
        Value is JSON-serialized.
        Returns False if Redis unavailable.
        """
        if not self.is_available:
            return False
        try:
            serialized = json.dumps(value)
            if ttl:
                await self._pool.setex(key, ttl, serialized)
            else:
                await self._pool.set(key, serialized)
            return True
        except Exception as e:
            logger.error("Redis SET failed", key=key, error=str(e))
            self._healthy = False
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a key's value (JSON-deserialized).
        Returns None if key doesn't exist or Redis unavailable.
        """
        if not self.is_available:
            return None
        try:
            data = await self._pool.get(key)
            if data is None:
                return None
            return json.loads(data)
        except Exception as e:
            logger.error("Redis GET failed", key=key, error=str(e))
            self._healthy = False
            return None

    async def delete(self, key: str) -> bool:
        """Delete a key."""
        if not self.is_available:
            return False
        try:
            await self._pool.delete(key)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.is_available:
            return False
        try:
            return bool(await self._pool.exists(key))
        except Exception:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Set/update TTL on a key."""
        if not self.is_available:
            return False
        try:
            await self._pool.expire(key, ttl)
            return True
        except Exception:
            return False

    async def incr(self, key: str) -> Optional[int]:
        """Atomic increment."""
        if not self.is_available:
            return None
        try:
            return await self._pool.incr(key)
        except Exception:
            return None

    # ============================================================
    # Rate Limiting (Sliding Window via Sorted Sets)
    # ============================================================

    async def rate_limit_check(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using Redis sorted set sliding window.
        
        Args:
            key: Rate limit key (e.g., "ratelimit:api:192.168.1.1")
            max_requests: Maximum allowed in window
            window_seconds: Window size in seconds
            
        Returns:
            Tuple of (is_limited, remaining, reset_timestamp)
        """
        if not self.is_available:
            # Fail open if Redis is down (allow request)
            return False, max_requests, 0

        import time
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._pool.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current entries
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {f"{now}": now})
            # Set TTL on the key
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]  # zcard result

            if current_count >= max_requests:
                # Get oldest entry to calculate reset time
                oldest = await self._pool.zrange(key, 0, 0, withscores=True)
                reset_time = int(oldest[0][1] + window_seconds) if oldest else int(now + window_seconds)
                return True, 0, reset_time

            remaining = max_requests - current_count - 1
            reset_time = int(now + window_seconds)
            return False, remaining, reset_time

        except Exception as e:
            logger.error("Redis rate limit check failed", error=str(e))
            # Fail open
            return False, max_requests, 0

    # ============================================================
    # Pub/Sub (for WebSocket broadcast across instances)
    # ============================================================

    async def publish(self, channel: str, message: Any) -> bool:
        """Publish a message to a Redis channel."""
        if not self.is_available:
            return False
        try:
            serialized = json.dumps(message)
            await self._pool.publish(channel, serialized)
            return True
        except Exception as e:
            logger.error("Redis PUBLISH failed", channel=channel, error=str(e))
            return False

    async def subscribe(self, channel: str, callback) -> None:
        """
        Subscribe to a Redis channel and call callback for each message.
        Runs in background — call in an asyncio.create_task().
        """
        if not self.is_available:
            return

        try:
            pubsub = self._pool.pubsub()
            await pubsub.subscribe(channel)
            logger.info("Subscribed to Redis channel", channel=channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await callback(data)
                    except Exception as e:
                        logger.error("Pub/Sub callback error", error=str(e))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Redis subscription error", channel=channel, error=str(e))

    # ============================================================
    # Session Operations (convenience methods)
    # ============================================================

    async def set_session(self, session_id: str, data: dict, ttl: int = 3600) -> bool:
        """Store a session with TTL."""
        return await self.set(f"session:{session_id}", data, ttl=ttl)

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve a session."""
        return await self.get(f"session:{session_id}")

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        return await self.delete(f"session:{session_id}")

    async def extend_session(self, session_id: str, ttl: int = 3600) -> bool:
        """Extend session TTL (on activity)."""
        return await self.expire(f"session:{session_id}", ttl)


# Global singleton instance
redis_manager = RedisManager()
