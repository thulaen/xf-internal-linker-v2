"""``roster()`` — read-only summary of every connected helper PC.

Powers the ``/api/helpers/`` endpoint, the Confidence Meter contributor
(Section 4.6.10), and the future Group Q.19 ``/diagnostics`` "Connected
helpers" card. Reads from the existing ``HelperNode`` model (no new
storage) and decorates with a couple of derived fields the operator
cares about (heartbeat age and free-disk fraction).

Plain-English: returns a list of "right now, this is the helper roster"
records. Each record says what the helper can do, what it's currently
doing, and how long since it last spoke. Cached 60 s in Redis so
dashboards / Confidence Meter calls are cheap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


CACHE_KEY = "helpers.roster"
CACHE_TTL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class HelperSummary:
    """One helper's right-now state, shaped for the operator UI."""

    name: str
    role: str
    status: str  # online | busy | unhealthy | offline
    accepting_work: bool
    heartbeat_age_seconds: int | None
    cpu_pct: float
    ram_pct: float
    active_jobs: int
    queued_jobs: int
    allowed_queues: list[str] = field(default_factory=list)
    allowed_job_types: list[str] = field(default_factory=list)
    warmed_model_keys: list[str] = field(default_factory=list)
    capabilities: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RosterSnapshot:
    """Whole-roster view used by Confidence Meter + /api/helpers/."""

    helpers: list[HelperSummary]
    online_count: int
    accepting_work_count: int
    sampled_at: str  # ISO 8601


def roster(*, force_refresh: bool = False) -> RosterSnapshot:
    """Return the current helper roster (cached 60 s)."""
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached
    snapshot = _build_roster()
    cache.set(CACHE_KEY, snapshot, CACHE_TTL_SECONDS)
    return snapshot


def _build_roster() -> RosterSnapshot:
    try:
        from apps.core.models import HelperNode
    except Exception:
        logger.debug("roster: HelperNode model unavailable", exc_info=True)
        return RosterSnapshot(
            helpers=[],
            online_count=0,
            accepting_work_count=0,
            sampled_at=timezone.now().isoformat(),
        )

    now = timezone.now()
    helpers: list[HelperSummary] = []
    online = 0
    accepting = 0
    try:
        for node in HelperNode.objects.all():
            helpers.append(_node_to_summary(node, now))
            if node.status in ("online", "busy"):
                online += 1
            if node.accepting_work and node.status in ("online", "busy"):
                accepting += 1
    except Exception:
        logger.debug("roster: HelperNode iteration failed", exc_info=True)

    return RosterSnapshot(
        helpers=helpers,
        online_count=online,
        accepting_work_count=accepting,
        sampled_at=now.isoformat(),
    )


def _node_to_summary(node, now) -> HelperSummary:
    """Convert a HelperNode ORM row to the read-shaped HelperSummary."""
    heartbeat_age: int | None = None
    if node.last_heartbeat:
        heartbeat_age = int((now - node.last_heartbeat).total_seconds())

    caps = node.capabilities or {}
    return HelperSummary(
        name=node.name,
        role=node.role,
        status=node.status,
        accepting_work=node.accepting_work,
        heartbeat_age_seconds=heartbeat_age,
        cpu_pct=float(node.cpu_pct or 0.0),
        ram_pct=float(node.ram_pct or 0.0),
        active_jobs=int(node.active_jobs or 0),
        queued_jobs=int(node.queued_jobs or 0),
        allowed_queues=list(node.allowed_queues or []),
        allowed_job_types=list(node.allowed_job_types or []),
        warmed_model_keys=list(node.warmed_model_keys or []),
        capabilities=dict(caps),
    )
