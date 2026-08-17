"""
Resilience patterns for external service calls.
Provides:
- Configurable timeouts
- Exponential backoff retry
- Circuit breaker (prevents cascading failures)

Usage:
    from services.resilience import CircuitBreaker, with_retry

    breaker = CircuitBreaker("bedrock", failure_threshold=3, recovery_timeout=30)

    @with_retry(max_attempts=3, base_delay=1.0)
    async def call_bedrock():
        async with breaker:
            result = await actual_bedrock_call()
        return result
"""

import asyncio
import time
import functools
from typing import Optional, Callable
from enum import Enum

import structlog

logger = structlog.get_logger()


class CircuitState(str, Enum):
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing — reject requests immediately
    HALF_OPEN = "half_open"    # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern.
    Prevents repeated calls to a failing service.

    States:
    - CLOSED: Normal operation. Failures increment counter.
    - OPEN: Service assumed down. Requests fail immediately without calling.
    - HALF_OPEN: After recovery_timeout, allow one test request.

    Args:
        name: Identifier for logging
        failure_threshold: Failures before opening circuit (default: 3)
        recovery_timeout: Seconds before trying again (default: 30)
        success_threshold: Successes in HALF_OPEN to close circuit (default: 1)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._last_state_change: float = time.time()

    @property
    def state(self) -> CircuitState:
        """Current circuit state (may auto-transition to HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(f"Circuit breaker [{self.name}] → HALF_OPEN (testing recovery)")
        return self._state

    @property
    def is_available(self) -> bool:
        """Whether requests should be allowed."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(f"Circuit breaker [{self.name}] → CLOSED (service recovered)")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0  # Reset on success

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during test — go back to OPEN
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit breaker [{self.name}] → OPEN (test failed)")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker [{self.name}] → OPEN "
                f"(threshold {self.failure_threshold} reached)"
            )

    async def __aenter__(self):
        """Check circuit before executing."""
        if not self.is_available:
            raise CircuitOpenError(
                f"Circuit breaker [{self.name}] is OPEN. "
                f"Service assumed unavailable. Retry after {self.recovery_timeout}s."
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Record result after execution."""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        return False  # Don't suppress exceptions


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator for exponential backoff retry.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay cap
        backoff_factor: Multiplier for each retry
        retryable_exceptions: Exception types that trigger retry
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except CircuitOpenError:
                    # Don't retry if circuit is open
                    raise
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"Retry {attempt}/{max_attempts} for {func.__name__}",
                            error=str(e),
                            next_delay=delay,
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}",
                            error=str(e),
                        )

            raise last_exception

        return wrapper
    return decorator


async def with_timeout(coro, timeout_seconds: float, fallback=None):
    """
    Execute a coroutine with a timeout.
    Returns fallback value if timeout occurs.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(f"Operation timed out after {timeout_seconds}s")
        if fallback is not None:
            return fallback
        raise
