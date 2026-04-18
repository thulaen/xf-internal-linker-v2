"""Helper-node routing engine.

Picks the best HelperNode for a given job based on:
  - capability match (queues, job types, time policy, GPU / RAM / kernels)
  - recent heartbeat and maintenance mode
  - current multi-resource load (CPU, RAM, GPU/VRAM, active slots)

Returns ``None`` when no suitable helper is available so the caller can stay on
the primary coordinator. This module stays pure Python + Django ORM so it can
be unit tested without Celery.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

# A helper is considered alive if its heartbeat is newer than this.
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
              - "cpu_cores" (numeric >=)
              - "ram_gb" (numeric >=)
              - "network_quality" (string equality)
              - "max_network_rtt_ms" (numeric <=)
              - "gpu_required" (boolean)
              - "native_kernels_healthy" (boolean equality)
              - "warmed_model_key" (membership test)
              - "demand_cpu" / "demand_ram_gb" / "demand_gpu_vram_gb"
                (routing-only demand hints)
        now: injectable for tests; defaults to ``timezone.now()``.
    """
    from apps.core.models import HelperNode

    if now is None:
        now = timezone.now()
    fresh_cutoff = now - timedelta(seconds=HEARTBEAT_FRESH_SECONDS)

    qs = HelperNode.objects.filter(
        status__in=("online", "busy"),
        last_heartbeat__gte=fresh_cutoff,
    )

    candidates = []
    for node in qs:
        if not node.accepting_work:
            continue
        if not _in_allowed_list(node.allowed_queues, queue):
            continue
        if not _in_allowed_list(node.allowed_job_types, job_type):
            continue
        if not _time_policy_ok(node.time_policy, now):
            continue
        if required_capabilities and not _capabilities_ok(
            node=node,
            need=required_capabilities,
        ):
            continue
        candidates.append(node)

    if not candidates:
        return None

    def _score(node) -> tuple[float, float, int]:
        projected_load = _projected_routing_score(
            node=node,
            required_capabilities=required_capabilities or {},
        )
        heartbeat_age = (now - node.last_heartbeat).total_seconds()
        status_bias = 0 if node.status == "online" else 1
        return (projected_load, heartbeat_age, status_bias)

    candidates.sort(key=_score)
    winner = candidates[0]
    logger.info(
        "helper_router: chose %s for job_type=%s queue=%s (candidates=%d score=%.4f)",
        winner.name,
        job_type,
        queue,
        len(candidates),
        _score(winner)[0],
    )
    return winner


def _in_allowed_list(allowed: list | None, value: str) -> bool:
    """Empty / missing allowed list means "allow anything"."""
    if not allowed:
        return True
    return value in allowed


def _time_policy_ok(policy: str, now) -> bool:
    """Evaluate the helper's availability window against the current time."""
    if policy == "anytime":
        return True
    hour = timezone.localtime(now).hour
    if policy in {"nighttime", "maintenance"}:
        return hour >= 21 or hour < 6
    return True


# Keys that describe a job's resource DEMAND, not a capability floor the
# helper must satisfy. ``_capabilities_ok`` skips these so the caller can
# use the same dict for both capability matching and load projection.
_DEMAND_KEYS: frozenset[str] = frozenset(
    {"demand_cpu", "demand_ram_gb", "demand_gpu_vram_gb"}
)


def _check_warmed_model_key(have: dict[str, Any], required: Any) -> bool:
    return required in have["warmed_model_keys"]


def _check_gpu_required(have: dict[str, Any], required: Any) -> bool:
    if not bool(required):
        return True
    return bool(have.get("gpu_vram_gb"))


def _check_native_kernels_healthy(have: dict[str, Any], required: Any) -> bool:
    return bool(have.get("native_kernels_healthy")) == bool(required)


def _check_max_network_rtt_ms(have: dict[str, Any], required: Any) -> bool:
    value = have.get("network_rtt_ms")
    if value is None:
        return False
    try:
        return float(value) <= float(required)
    except (TypeError, ValueError):
        return False


# Explicit handlers for capability keys whose comparison is not a simple
# "have >= required" floor. Keys NOT in this map fall through to
# ``_check_floor``. Adding a new custom capability check means adding a
# row here; keeping the dispatcher flat keeps the main function cheap.
_CAPABILITY_HANDLERS: dict[str, Any] = {
    "warmed_model_key": _check_warmed_model_key,
    "gpu_required": _check_gpu_required,
    "native_kernels_healthy": _check_native_kernels_healthy,
    "max_network_rtt_ms": _check_max_network_rtt_ms,
}


def _check_floor(have: dict[str, Any], key: str, required: Any) -> bool:
    """Default rule: numeric ``have[key]`` must be >= ``required``.

    Falls back to equality for non-numeric values so tag-style capability
    requirements (e.g., ``"gpu_class": "A100"``) still work.
    """
    value = have.get(key)
    if value is None:
        return False
    try:
        return float(value) >= float(required)
    except (TypeError, ValueError):
        return value == required


def _capabilities_ok(*, node, need: dict[str, Any]) -> bool:
    """All required capability floors must be satisfied.

    Dispatches per-key into ``_CAPABILITY_HANDLERS`` for capabilities
    with custom comparison rules; any key not in that map uses
    ``_check_floor`` (numeric >= with equality fallback). This keeps
    the per-capability logic as named one-liners and keeps this main
    function's branching flat.
    """
    have = dict(node.capabilities or {})
    have["network_rtt_ms"] = node.network_rtt_ms
    have["native_kernels_healthy"] = node.native_kernels_healthy
    have["warmed_model_keys"] = node.warmed_model_keys or []

    for key, required in need.items():
        if key in _DEMAND_KEYS:
            continue
        handler = _CAPABILITY_HANDLERS.get(key)
        if handler is not None:
            if not handler(have, required):
                return False
        elif not _check_floor(have, key, required):
            return False
    return True


def _projected_routing_score(
    *,
    node,
    required_capabilities: dict[str, Any],
) -> float:
    """Return a DRF-style projected load score for this helper.

    Ghodsi et al. (NSDI 2011) define dominant-resource fairness in terms of a
    task's largest normalized resource share. We combine that dominant-share
    estimate with the helper's live slot/CPU/RAM/GPU pressure and pick the
    lowest projected maximum.
    """
    demand_cpu = _float_or(required_capabilities.get("demand_cpu"), 1.0)
    demand_ram = _float_or(required_capabilities.get("demand_ram_gb"), 1.0)
    demand_gpu = _float_or(required_capabilities.get("demand_gpu_vram_gb"), 0.0)

    caps = node.capabilities or {}
    usable_cpu = _float_or(caps.get("cpu_cores"), 0.0) * (
        max(float(node.cpu_cap_pct or 0), 0.0) / 100.0
    )
    usable_ram = _float_or(caps.get("ram_gb"), 0.0) * (
        max(float(node.ram_cap_pct or 0), 0.0) / 100.0
    )
    usable_gpu = _float_or(caps.get("gpu_vram_gb"), 0.0)

    cpu_share = demand_cpu / max(usable_cpu, 1e-6)
    ram_share = demand_ram / max(usable_ram, 1e-6)
    gpu_share = demand_gpu / max(usable_gpu, 1e-6) if demand_gpu > 0 else 0.0
    dominant_share = max(cpu_share, ram_share, gpu_share)

    slot_pressure = float(node.active_jobs or 0) / max(
        int(node.max_concurrency or 1), 1
    )
    cpu_pressure = float(node.cpu_pct or 0.0) / max(float(node.cpu_cap_pct or 1), 1.0)
    ram_pressure = float(node.ram_pct or 0.0) / max(float(node.ram_cap_pct or 1), 1.0)
    gpu_pressure = 0.0
    if node.gpu_util_pct is not None:
        gpu_pressure = max(gpu_pressure, float(node.gpu_util_pct or 0.0) / 100.0)
    if node.gpu_vram_used_mb and node.gpu_vram_total_mb:
        gpu_pressure = max(
            gpu_pressure,
            float(node.gpu_vram_used_mb) / max(float(node.gpu_vram_total_mb), 1.0),
        )

    effective_load = min(
        1.0, max(slot_pressure, cpu_pressure, ram_pressure, gpu_pressure)
    )
    return max(dominant_share, effective_load)


def _float_or(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value
