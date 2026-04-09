"""
Lightweight circuit breaker for external service calls.

Prevents cascading failures when an external service (C# HTTP Worker,
GA4, XenForo API, WordPress API) goes down.  Instead of waiting for
timeouts on every request, the breaker opens after N consecutive failures
and rejects calls immediately until a recovery probe succeeds.

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Type

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, name: str, seconds_remaining: float):
        self.name = name
        self.seconds_remaining = seconds_remaining
        super().__init__(
            f"Circuit '{name}' is OPEN — next probe in {seconds_remaining:.0f}s"
        )


class CircuitBreaker:
    """Thread-safe circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        expected_exceptions: list[Type[Exception]] | None = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.expected_exceptions = tuple(expected_exceptions or [Exception])

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

    # ── Public API ──────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* through the breaker.  Raises CircuitBreakerOpen if open."""
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                remaining = self.recovery_timeout - (time.monotonic() - self._last_failure_time)
                raise CircuitBreakerOpen(self.name, max(0, remaining))

        try:
            result = fn(*args, **kwargs)
        except self.expected_exceptions:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    # ── Internal helpers ────────────────────────────────────────

    def _maybe_transition_to_half_open(self) -> None:
        """Must be called while holding self._lock."""
        if (
            self._state == CircuitState.OPEN
            and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info("Circuit '%s' entering HALF_OPEN", self.name)

    def _on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    logger.info("Circuit '%s' CLOSED (recovered)", self.name)

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    "Circuit '%s' OPEN after %d failures",
                    self.name,
                    self._failure_count,
                )


# ── Pre-configured breakers for each external service ──────────

http_worker_breaker = CircuitBreaker(
    name="http_worker",
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=2,
    expected_exceptions=[TimeoutError, OSError, ConnectionError],
)

ga4_breaker = CircuitBreaker(
    name="ga4",
    failure_threshold=3,
    recovery_timeout=300,
    success_threshold=1,
    expected_exceptions=[TimeoutError, OSError, ConnectionError],
)

xenforo_breaker = CircuitBreaker(
    name="xenforo",
    failure_threshold=10,
    recovery_timeout=300,
    success_threshold=3,
    expected_exceptions=[TimeoutError, OSError, ConnectionError],
)

wordpress_breaker = CircuitBreaker(
    name="wordpress",
    failure_threshold=8,
    recovery_timeout=300,
    success_threshold=2,
    expected_exceptions=[TimeoutError, OSError, ConnectionError],
)
