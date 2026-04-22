"""Token-bucket rate limiter — pure Python, no external dependencies.

Per Turner's 1986 *IEEE Communications* paper "New directions in
communications (or which way to the information age?)". Models each
protected resource as a bucket of tokens:

- The bucket refills at a steady rate ``tokens_per_second``.
- The bucket caps at ``burst_capacity`` tokens — short bursts allowed.
- Every request removes ``cost`` tokens; when ``tokens < cost`` the
  caller is either rejected (``try_acquire``) or blocked until enough
  tokens regenerate (``wait_and_acquire``).

Distinct buckets per (host, endpoint) — held in an
:class:`InMemoryBucketRegistry`. For a multi-process deployment with
shared state the runner will later add a Redis-backed
``DistributedBucketRegistry``; the protocol below is deliberately
backend-agnostic so swapping implementations does not touch callers.

No shared mutable globals outside the default registry, which tests
can replace via ``DEFAULT_REGISTRY.clear()``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class BucketConfig:
    """Static config for one named bucket."""

    tokens_per_second: float
    burst_capacity: float

    def __post_init__(self) -> None:
        if self.tokens_per_second <= 0:
            raise ValueError("tokens_per_second must be > 0")
        if self.burst_capacity <= 0:
            raise ValueError("burst_capacity must be > 0")


@dataclass
class _BucketState:
    """Mutable state held by ``InMemoryBucketRegistry`` per key.

    Separated from :class:`BucketConfig` so tests can reset state
    without rebuilding configs.
    """

    config: BucketConfig
    tokens: float
    last_refill: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class BucketRegistry(Protocol):
    """Backend-agnostic registry — in-memory today, Redis-ready tomorrow."""

    def try_acquire(self, key: str, *, cost: float = 1.0) -> bool: ...

    def wait_and_acquire(
        self,
        key: str,
        *,
        cost: float = 1.0,
        timeout: float | None = None,
    ) -> bool: ...

    def available(self, key: str) -> float: ...


class InMemoryBucketRegistry:
    """Thread-safe per-process registry of named token buckets."""

    def __init__(self) -> None:
        self._buckets: dict[str, _BucketState] = {}
        self._configs: dict[str, BucketConfig] = {}
        # Registry-level lock covers dict mutation; per-bucket locks
        # cover token arithmetic so unrelated buckets never serialise.
        self._registry_lock = threading.Lock()

    def register(self, key: str, config: BucketConfig) -> None:
        """Register or replace the config for *key*.

        Replacing resets the bucket to full capacity — the old tokens
        would otherwise over-/under-count against the new rate.
        """
        with self._registry_lock:
            self._configs[key] = config
            self._buckets[key] = _BucketState(
                config=config,
                tokens=config.burst_capacity,
                last_refill=time.monotonic(),
            )

    def _get_or_default(self, key: str) -> _BucketState:
        """Return the state for *key*, using a safe per-second default if never registered."""
        state = self._buckets.get(key)
        if state is not None:
            return state
        # Unknown key: conservative default so callers never bypass the
        # limiter by calling with a typo. Explicit register() overrides.
        default = BucketConfig(tokens_per_second=1.0, burst_capacity=1.0)
        with self._registry_lock:
            state = self._buckets.get(key)
            if state is None:
                self._configs[key] = default
                state = _BucketState(
                    config=default,
                    tokens=default.burst_capacity,
                    last_refill=time.monotonic(),
                )
                self._buckets[key] = state
        return state

    def _refill(self, state: _BucketState, *, now: float) -> None:
        """Advance state.tokens for the time elapsed since last_refill."""
        elapsed = max(0.0, now - state.last_refill)
        if elapsed <= 0:
            return
        refill = elapsed * state.config.tokens_per_second
        state.tokens = min(state.config.burst_capacity, state.tokens + refill)
        state.last_refill = now

    def try_acquire(self, key: str, *, cost: float = 1.0) -> bool:
        """Remove *cost* tokens immediately if available. Returns True on success."""
        if cost <= 0:
            raise ValueError("cost must be > 0")
        state = self._get_or_default(key)
        now = time.monotonic()
        with state.lock:
            self._refill(state, now=now)
            if state.tokens >= cost:
                state.tokens -= cost
                return True
            return False

    def wait_and_acquire(
        self,
        key: str,
        *,
        cost: float = 1.0,
        timeout: float | None = None,
    ) -> bool:
        """Block until *cost* tokens are available, up to *timeout* seconds.

        Returns True on acquisition, False on timeout. ``timeout=None``
        waits indefinitely, which the callers should never pass in
        production code — the caller's own Celery task timeout covers
        the upper bound.
        """
        if cost <= 0:
            raise ValueError("cost must be > 0")
        state = self._get_or_default(key)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            now = time.monotonic()
            with state.lock:
                self._refill(state, now=now)
                if state.tokens >= cost:
                    state.tokens -= cost
                    return True
                deficit = cost - state.tokens
                wait_s = deficit / state.config.tokens_per_second
            if deadline is not None and now + wait_s > deadline:
                return False
            # Sleep outside the lock so other buckets keep draining.
            time.sleep(min(wait_s, 0.2))

    def available(self, key: str) -> float:
        """Return the number of tokens currently available (refill included)."""
        state = self._get_or_default(key)
        now = time.monotonic()
        with state.lock:
            self._refill(state, now=now)
            return state.tokens

    def clear(self) -> None:
        """Test-only: forget every bucket."""
        with self._registry_lock:
            self._buckets.clear()
            self._configs.clear()


#: One process-wide registry so callers in different modules share the
#: same buckets without plumbing a handle around. Tests reset state via
#: ``DEFAULT_REGISTRY.clear()``.
DEFAULT_REGISTRY: InMemoryBucketRegistry = InMemoryBucketRegistry()
