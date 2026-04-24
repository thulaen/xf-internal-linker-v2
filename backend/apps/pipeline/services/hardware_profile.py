"""Hardware-aware dynamic batch sizing (plan Part 8a, FR-233).

Detects RAM / CPU / VRAM at module import time (cheap; cached) and recommends
an embedding batch size scaled to the machine and the target vector dimension.

Research grounding (docstring only — full citations in FR-233 spec):
  * Smith et al. 2018 — "Don't decay the learning rate, increase the batch
    size" (ICLR 2018). Dynamic batch sizing based on available memory.
  * Micikevicius et al. 2018 — "Mixed Precision Training" (ICLR 2018). FP16
    halves memory cost; our GPU path already uses fp16 for local models.
  * NVIDIA Triton Inference Server — public prior art for memory-scaled batching.

Performance contract:
  * Detection costs one ``psutil.virtual_memory()`` call + one
    ``torch.cuda.mem_get_info()`` when CUDA is available. Both are ~microseconds.
  * Results cached per-process; a single ``_HardwareProfileCache`` object holds
    them, invalidated only by explicit ``refresh()``.
  * ``recommended_batch_size()`` is pure arithmetic — no I/O, no allocation.

Tier table (auto-detected; overridable via ``AppSetting("performance.profile_override")``):

    Low         <8 GB RAM, no GPU
    Medium      8–16 GB RAM or integrated GPU
    High        16–32 GB RAM, dGPU >=4 GB VRAM
    Workstation 32+ GB RAM, dGPU >=8 GB VRAM

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
    vram_gb: float         # 0.0 if no CUDA device
    has_cuda: bool
    tier: Tier

    def describe(self) -> str:
        gpu_part = f"{self.vram_gb:.1f} GB VRAM" if self.has_cuda else "no GPU"
        return (
            f"tier={self.tier} ram={self.ram_gb:.1f}GB cores={self.cpu_cores} {gpu_part}"
        )


_cached_profile: HardwareProfile | None = None


def detect_profile(*, force_refresh: bool = False) -> HardwareProfile:
    """Detect the hardware profile and return it (cached across calls)."""
    global _cached_profile
    if _cached_profile is not None and not force_refresh:
        return _cached_profile

    ram_gb = _detect_ram_gb()
    cpu_cores = _detect_cpu_cores()
    has_cuda, vram_gb = _detect_gpu()
    tier = _classify_tier(ram_gb=ram_gb, has_cuda=has_cuda, vram_gb=vram_gb)

    # AppSetting override (e.g. "low" to test low-end behaviour on a workstation).
    override = _read_setting_override()
    if override in ("low", "medium", "high", "workstation"):
        tier = override  # type: ignore[assignment]

    profile = HardwareProfile(
        ram_gb=ram_gb,
        cpu_cores=cpu_cores,
        vram_gb=vram_gb,
        has_cuda=has_cuda,
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
    except Exception:
        return 8.0


def _detect_cpu_cores() -> int:
    return os.cpu_count() or 1


def _detect_gpu() -> tuple[bool, float]:
    """Return (has_cuda, vram_gb)."""
    try:
        import torch
    except ImportError:
        return False, 0.0
    try:
        if not torch.cuda.is_available():
            return False, 0.0
        # Use the primary device; multi-GPU hosts pick card 0.
        free, total = torch.cuda.mem_get_info()
        return True, float(total) / 1e9
    except Exception:
        return False, 0.0


def _classify_tier(*, ram_gb: float, has_cuda: bool, vram_gb: float) -> Tier:
    if ram_gb < 8:
        return "low"
    if ram_gb < 16:
        # Medium if no discrete GPU; still medium if only integrated GPU reported.
        if has_cuda and vram_gb >= 4:
            return "high"
        return "medium"
    if ram_gb < 32:
        if has_cuda and vram_gb >= 4:
            return "high"
        return "medium"
    # 32+ GB RAM
    if has_cuda and vram_gb >= 8:
        return "workstation"
    if has_cuda and vram_gb >= 4:
        return "high"
    return "high"


def _tier_cap(tier: Tier) -> int:
    return {
        "low": 32,
        "medium": 64,
        "high": 128,
        "workstation": 256,
    }.get(tier, 64)


def _read_setting_override() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key="performance.profile_override").first()
        if row and row.value:
            return str(row.value).strip().lower()
    except Exception:
        pass
    return ""


__all__ = [
    "HardwareProfile",
    "detect_profile",
    "recommended_batch_size",
    "refresh",
]
