"""Unit tests for the Phase 2 worker-cap helpers in hardware_profile.

The helpers compute MAX_JOBS_FAST and MAX_JOBS_HEAVY which the pre-commit /
pre-push hooks export so heavy tools (mutation / fuzz / sanitizers) can
honour the project's "max 2 or 3 workers for heavy band" policy without
hardcoding worker counts.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.hardware_profile import (
    HardwareProfile,
    max_jobs_fast,
    max_jobs_heavy,
)


def _profile(tier: str) -> HardwareProfile:
    return HardwareProfile(
        ram_gb=16.0,
        cpu_cores=8,
        vram_gb=0.0,
        has_cuda=False,
        tier=tier,  # type: ignore[arg-type]
    )


class MaxJobsFastTests(SimpleTestCase):
    def test_low_tier_returns_two(self) -> None:
        self.assertEqual(max_jobs_fast(_profile("low")), 2)

    def test_medium_tier_returns_four(self) -> None:
        self.assertEqual(max_jobs_fast(_profile("medium")), 4)

    def test_high_tier_returns_six(self) -> None:
        self.assertEqual(max_jobs_fast(_profile("high")), 6)

    def test_workstation_tier_returns_eight(self) -> None:
        self.assertEqual(max_jobs_fast(_profile("workstation")), 8)

    def test_unknown_tier_falls_back_to_two(self) -> None:
        bogus = HardwareProfile(
            ram_gb=4.0, cpu_cores=2, vram_gb=0.0, has_cuda=False,
            tier="bogus",  # type: ignore[arg-type]
        )
        self.assertEqual(max_jobs_fast(bogus), 2)


class MaxJobsHeavyTests(SimpleTestCase):
    def test_heavy_cap_is_min_three_below_fast(self) -> None:
        # Heavy cap = min(3, fast) → never above 3 regardless of tier.
        self.assertEqual(max_jobs_heavy(_profile("low")), 2)         # fast=2 → heavy=2
        self.assertEqual(max_jobs_heavy(_profile("medium")), 3)      # fast=4 → heavy=3
        self.assertEqual(max_jobs_heavy(_profile("high")), 3)        # fast=6 → heavy=3
        self.assertEqual(max_jobs_heavy(_profile("workstation")), 3) # fast=8 → heavy=3

    def test_heavy_never_exceeds_three(self) -> None:
        for tier in ("low", "medium", "high", "workstation"):
            with self.subTest(tier=tier):
                self.assertLessEqual(max_jobs_heavy(_profile(tier)), 3)

    def test_heavy_floor_is_one(self) -> None:
        bogus = HardwareProfile(
            ram_gb=1.0, cpu_cores=1, vram_gb=0.0, has_cuda=False,
            tier="bogus",  # type: ignore[arg-type]
        )
        self.assertGreaterEqual(max_jobs_heavy(bogus), 1)
