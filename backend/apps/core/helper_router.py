"""
Helper-node routing engine (plan item 18).

Picks the best HelperNode for a given job based on:
  - capability match (allowed_queues, allowed_job_types, time_policy, GPU / VRAM
    when required)
  - recent heartbeat (dead nodes must never be picked)
  - current load (lower ``active_job_count`` wins; ties broken by status)

Returns ``None`` when no suitable helper is available — the caller stays on the
main coordinator in that case. This file is deliberately pure Python + Django
ORM so it can be unit tested without Celery.

Usage:
    helper = select_best_helper_node(job_type="embeddings", queue="embeddings",
                                     required_capabilities={"gpu_vram_gb": 4})
    if helper:
        # Dispatch onto the helper's worker. Implementation of the actual
        # dispatch stays in the caller's task module; this module only picks.
        ...
    else:
        # Fall back to the main coordinator.
        ...
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

# A helper is considered alive if its heartbeat is newer than this.
# Matches the "30 sec staleness" concept in docs/PERFORMANCE.md without being
# so tight that brief network hiccups evict healthy workers.
HEARTBEAT_FRESH_SECONDS = 120


def select_best_helper_node(
    *,
    job_type: str,
    queue: str,
    required_capabilities: dict[str, Any] | None = None,
    now=None,
):
    """Return the best-fit HelperNode, or None if none qualifies.

    Arguments:
        job_type: e.g. "embeddings", "sync", "pipeline". Must appear in the
            node's ``allowed_job_types``.
        queue: e.g. "pipeline", "embeddings", "default". Must appear in the
            node's ``allowed_queues``.
        required_capabilities: optional dict of ``{capability_key: min_value}``
            pairs that must be satisfied. Supported keys today:
              - "gpu_vram_gb" (numeric >=)
              - "cpu_cores"    (numeric >=)
              - "ram_gb"       (numeric >=)
              - "network_quality" (str equality)
        now: injectable for tests; defaults to ``timezone.now()``.
    """
    from apps.core.models import HelperNode

    if now is None:
        now = timezone.now()
    fresh_cutoff = now - timedelta(seconds=HEARTBEAT_FRESH_SECONDS)

    # Coarse prefilter by status + queue + job_type + heartbeat.
    qs = HelperNode.objects.filter(
        status__in=("online", "busy"),
        last_heartbeat__gte=fresh_cutoff,
    )

    candidates = []
    for node in qs:
        if not _in_allowed_list(node.allowed_queues, queue):
            continue
        if not _in_allowed_list(node.allowed_job_types, job_type):
            continue
        if not _time_policy_ok(node.time_policy, now):
            continue
        if required_capabilities and not _capabilities_ok(
            node.capabilities, required_capabilities
        ):
            continue
        candidates.append(node)

    if not candidates:
        return None

    # Sort by: status='online' (0) before 'busy' (1), then lower active load.
    def _score(node) -> tuple[int, int]:
        return (0 if node.status == "online" else 1, _active_job_count(node))

    candidates.sort(key=_score)
    winner = candidates[0]
    logger.info(
        "helper_router: chose %s for job_type=%s queue=%s (candidates=%d)",
        winner.name,
        job_type,
        queue,
        len(candidates),
    )
    return winner


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _in_allowed_list(allowed: list | None, value: str) -> bool:
    """Empty / missing allowed list means "allow anything" (no restriction)."""
    if not allowed:
        return True
    return value in allowed


def _time_policy_ok(policy: str, now) -> bool:
    """Evaluate the helper's availability window against the current time."""
    if policy == "anytime":
        return True
    hour = timezone.localtime(now).hour
    if policy == "nighttime":
        # docs/PERFORMANCE.md: 21:00–06:00 UTC. Evaluated in local tz here so
        # operators on different timezones get predictable behaviour.
        return hour >= 21 or hour < 6
    if policy == "maintenance":
        # Conservative: only allow during a narrow maintenance slot.
        # Explicit schedule is operator-configured; default to nighttime behaviour.
        return hour >= 21 or hour < 6
    return True  # unknown policy — be permissive rather than block work


def _capabilities_ok(have: dict, need: dict) -> bool:
    """All required capability floors must be satisfied."""
    for key, required in need.items():
        value = have.get(key)
        if value is None:
            return False
        # Numeric comparison when both look numeric.
        try:
            if float(value) < float(required):
                return False
        except (TypeError, ValueError):
            # Fall back to equality for non-numeric values (e.g. network_quality).
            if value != required:
                return False
    return True


def _active_job_count(node) -> int:
    """Approximate active-job count for load sorting.

    HelperNode doesn't track live job count directly today, so we approximate:
    'busy' status counts as 1 unit of load, 'online' counts as 0. When a real
    job-count field is added, replace this helper with a proper read.
    """
    return 1 if node.status == "busy" else 0
