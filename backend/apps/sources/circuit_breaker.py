"""Source-layer circuit-breaker re-export.

The mature implementation lives in ``apps.pipeline.services.circuit_breaker``
(three-state machine, per-service config, thread-safe). Rather than
duplicate that logic, the source layer exposes the same primitives
under a shorter dotted path so new outbound integrations don't need
to reach across app boundaries.

Per the PR-C duplication audit, the source layer reuses the existing
breaker — it does NOT fork it. Any behaviour change lands in the
upstream module.

Reference: Nygard, *Release It!* (Pragmatic Bookshelf, 2007), "Stability
Patterns: Circuit Breaker".
"""

from __future__ import annotations

from apps.pipeline.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    ga4_breaker,
    wordpress_breaker,
    xenforo_breaker,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "ga4_breaker",
    "wordpress_breaker",
    "xenforo_breaker",
]
