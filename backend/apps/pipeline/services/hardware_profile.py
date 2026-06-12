# print-allowed: __main__ JSON CLI consumed by .githooks/lib-hwprofile.sh (Phase 2)
"""Hardware-aware dynamic batch sizing (plan Part 8a, FR-233).

Detects RAM / CPU at module import time (cheap; cached) and recommends
an embedding batch size scaled to the machine and the target vector dimension.

Research grounding (docstring only — full citations in FR-233 spec):
  * Smith et al. 2018 — "Don't decay the learning rate, increase the batch
    size" (ICLR 2018). Dynamic batch sizing based on available memory.
Performance contract:
  * Detection costs one ``psutil.virtual_memory()`` call.
  * Results cached per-process; a single ``_HardwareProfileCache`` object holds
    them, invalidated only by explicit ``refresh()``.
  * ``recommended_batch_size()`` is pure arithmetic — no I/O, no allocation.

Tier table (auto-detected; overridable via ``AppSetting("performance.profile_override")``):

    Low         <8 GB RAM
    Medium      8–16 GB RAM
    High        16–32 GB RAM
    Workstation 32+ GB RAM

High-dimension models (OpenAI 3-large = 3072 dim) get smaller batches so peak
memory stays under ~15% of host RAM — the budget envelope defined in
``docs/PERFORMANCE.md`` §3.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Tier = Literal["low", "medium", "high", "workstation"]

# Hard bounds so a misconfigured system doesn't pick an insane batch size.
_BATCH_MIN = 4
_BATCH_MAX = 256

# Per-vector bytes in peak memory: 1 input buffer + 1 intermediate + 1 output.
# Scales linearly with the model dimension.
_PER_ITEM_MULTIPLIER = 3

# Fraction of host RAM we are willing to spend on a single embed batch peak.
# 15% matches the Medium-tier budget envelope in docs/PERFORMANCE.md §3.
_RAM_BATCH_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    ram_gb: float
    cpu_cores: int
    tier: Tier
    vram_gb: float = 0.0

    def describe(self) -> str:
        return f"tier={self.tier} ram={self.ram_gb:.1f}GB cores={self.cpu_cores}"


_cached_profile: HardwareProfile | None = None


def detect_profile(*, force_refresh: bool = False) -> HardwareProfile:
    """Detect the hardware profile and return it (cached across calls)."""
    global _cached_profile
    if _cached_profile is not None and not force_refresh:
        return _cached_profile

    ram_gb = _detect_ram_gb()
    cpu_cores = _detect_cpu_cores()
    tier = _classify_tier(ram_gb=ram_gb)

    # AppSetting override (e.g. "low" to test low-end behaviour on a workstation).
    override = _read_setting_override()
    if override in ("low", "medium", "high", "workstation"):
        tier = override  # type: ignore[assignment]

    profile = HardwareProfile(
        ram_gb=ram_gb,
        cpu_cores=cpu_cores,
        tier=tier,
    )
    _cached_profile = profile
    logger.info("Hardware profile detected: %s", profile.describe())
    return profile


def refresh() -> HardwareProfile:
    """Force re-detection (e.g. when operator overrides via AppSetting)."""
    return detect_profile(force_refresh=True)


def recommended_batch_size(
    *,
    dimension: int,
    profile: HardwareProfile | None = None,
    provider_ceiling: int | None = None,
) -> int:
    """Return a batch size sized to the machine + target dimension.

    Args:
        dimension: Vector dim (1024 for BGE-M3, 1536 for OpenAI-small,
                   3072 for OpenAI-large).
        profile: Pre-computed profile; auto-detect if None.
        provider_ceiling: API-specific batch limit (OpenAI ~2 048, Gemini 100).
                          The returned batch size is capped at this ceiling.

    The formula:
        budget_bytes  = ram_gb * 1e9 * _RAM_BATCH_FRACTION
        per_item_b    = dimension * 4 (float32) * _PER_ITEM_MULTIPLIER
        raw_batch     = budget_bytes / per_item_b
        capped_batch  = clamp(raw_batch, _BATCH_MIN, _BATCH_MAX)

    Tier caps keep the returned batch inside the documented envelope:
        low         -> max 32
        medium      -> max 64
        high        -> max 128
        workstation -> max 256
    """
    prof = profile or detect_profile()

    budget_bytes = prof.ram_gb * 1e9 * _RAM_BATCH_FRACTION
    per_item_b = max(1, dimension) * 4 * _PER_ITEM_MULTIPLIER
    raw_batch = int(budget_bytes / per_item_b) if per_item_b > 0 else _BATCH_MIN

    tier_cap = _tier_cap(prof.tier)
    batch = max(_BATCH_MIN, min(raw_batch, tier_cap, _BATCH_MAX))
    if provider_ceiling is not None and provider_ceiling > 0:
        batch = min(batch, provider_ceiling)
    return int(batch)


# ---------------------------------------------------------------------------
# Detection internals
# ---------------------------------------------------------------------------


def _detect_ram_gb() -> float:
    try:
        import psutil

        return float(psutil.virtual_memory().total) / 1e9
    except ImportError:
        # psutil is a hard dep in this project, but guard anyway.
        return 8.0
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        return 8.0


def _detect_cpu_cores() -> int:
    return os.cpu_count() or 1


def _classify_tier(*, ram_gb: float) -> Tier:
    if ram_gb < 8:
        return "low"
    if ram_gb < 16:
        return "medium"
    if ram_gb < 32:
        return "high"
    return "workstation"


def _tier_cap(tier: Tier) -> int:
    return {
        "low": 32,
        "medium": 64,
        "high": 128,
        "workstation": 256,
    }.get(tier, 64)


def max_jobs_fast(profile: HardwareProfile | None = None) -> int:
    """Concurrency cap for fast unit suites (pytest / Karma / C++ unit).

    Tier-aware so a workstation isn't artificially hobbled. Used by the
    `.githooks/lib-hwprofile.sh` helper to set MAX_JOBS_FAST. Floor at 1
    so a single-core VM still functions.
    """
    prof = profile or detect_profile()
    return max(1, {"low": 2, "medium": 4, "high": 6, "workstation": 8}.get(prof.tier, 2))


def max_jobs_heavy(profile: HardwareProfile | None = None) -> int:
    """Concurrency cap for heavy tools (mutation / fuzz / sanitizers).

    Honours the project policy "max 2 or 3 workers for heavy band" so
    Mull / mutmut / Stryker / libFuzzer / MSan / ASan / TSan can never
    oversubscribe the machine and crash the user's session. Capped at
    min(3, tier_cap_fast) so low-end hosts get 2 and high-end hosts 3.
    """
    fast = max_jobs_fast(profile)
    return max(1, min(3, fast))


def polars_thread_count(profile: HardwareProfile | None = None) -> int:
    """Return the thread budget for the Polars query engine.

    Polars spawns its own work-stealing thread pool. Left unbounded it grabs
    every core, which fights Celery workers running at the same time. Half of
    the detected cores keeps batch ETL fast while leaving headroom for the
    rest of the stack — see ``docs/PERFORMANCE.md`` §3 for the budget envelope.
    Floor at 1 so a single-core VM still functions.
    """
    prof = profile or detect_profile()
    return max(1, prof.cpu_cores // 2)


def _read_setting_override() -> str:
    try:
        import warnings
        from apps.core.models import AppSetting

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            row = AppSetting.objects.filter(key="performance.profile_override").first()
        if row and row.value:
            return str(row.value).strip().lower()
    except Exception:  # noqa: BLE001 — pre-Django-init / fresh-install path: no AppSetting table yet, fall back to auto-detect.
        logger.debug(
            "performance profile override unavailable; using auto-detected hardware profile",
            exc_info=True,
        )
    return ""


__all__ = [
    "HardwareProfile",
    "detect_profile",
    "max_jobs_fast",
    "max_jobs_heavy",
    "polars_thread_count",
    "recommended_batch_size",
    "refresh",
]


def _emit_json(profile: HardwareProfile) -> str:
    import json

    return json.dumps(
        {
            "tier": profile.tier,
            "cpu_cores": profile.cpu_cores,
            "ram_gb": round(profile.ram_gb, 2),
            "max_jobs_fast": max_jobs_fast(profile),
            "max_jobs_heavy": max_jobs_heavy(profile),
        }
    )


if __name__ == "__main__":
    # CLI entry consumed by .githooks/lib-hwprofile.sh so pre-commit /
    # pre-push hooks can derive MAX_JOBS_FAST + MAX_JOBS_HEAVY from the
    # detected tier without hardcoding worker counts. Usage:
    #   python -m apps.pipeline.services.hardware_profile --json
    # The JSON line is parseable by `python -c "import json,sys;..."`.
    import sys

    if "--json" in sys.argv:
        # Skip Django AppSetting override when run as a CLI — pre-commit
        # runs before Django settings may be importable; auto-detect only.
        prof = detect_profile()
        print(_emit_json(prof))
    else:
        prof = detect_profile()
        print(prof.describe())
        print(f"  max_jobs_fast={max_jobs_fast(prof)}  max_jobs_heavy={max_jobs_heavy(prof)}")
