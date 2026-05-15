"""Tests for the disk_pressure circuit breaker.

The module is small (≤200 lines) so the test surface is also small:
- the guard raises when free disk < write + margin
- the guard does NOT raise when free disk >= write + margin
- current_state() classifies free GB into GREEN/YELLOW/RED/CRITICAL bands
- refresh_disk_pressure_state() emits an alert on first transition only
- the dedup window suppresses repeat alerts at the same state
"""
from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.pipeline.services import disk_pressure


def _fake_usage(free_gb: float):
    """Build the SimpleNamespace shutil.disk_usage returns."""
    from types import SimpleNamespace

    gb = 1024 ** 3
    total = max(free_gb, 100.0) * gb
    return SimpleNamespace(free=free_gb * gb, total=total, used=total - free_gb * gb)


class DiskPressureRequireFreeDiskTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_raises_when_free_below_write_plus_margin(self) -> None:
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=3.0)):
            with self.assertRaises(disk_pressure.DiskPressureError):
                disk_pressure.require_free_disk(
                    estimated_bytes=2 * 1024 ** 3,  # 2 GB write
                    safety_margin_gb=5,             # 5 GB margin
                )                                   # needs 7 GB; only 3 GB free

    def test_passes_when_free_above_threshold(self) -> None:
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=20.0)):
            # 1 GB write + 5 GB margin = 6 GB needed; 20 GB free — passes.
            disk_pressure.require_free_disk(
                estimated_bytes=1 * 1024 ** 3,
                safety_margin_gb=5,
            )

    def test_explicit_margin_overrides_default(self) -> None:
        # 12 GB free, 8 GB write, 3 GB margin = 11 GB needed → passes.
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=12.0)):
            disk_pressure.require_free_disk(
                estimated_bytes=8 * 1024 ** 3,
                safety_margin_gb=3,
            )
        # 12 GB free, 8 GB write, 5 GB margin = 13 GB needed → fails.
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=12.0)):
            with self.assertRaises(disk_pressure.DiskPressureError):
                disk_pressure.require_free_disk(
                    estimated_bytes=8 * 1024 ** 3,
                    safety_margin_gb=5,
                )


class DiskPressureClassificationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def _classify(self, free_gb: float) -> str:
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=free_gb)):
            cache.delete(disk_pressure._CACHE_KEY)
            return disk_pressure.current_state()

    def test_at_or_above_64gb_is_green(self) -> None:
        self.assertEqual(self._classify(64.0), "GREEN")

    def test_between_48_and_64gb_is_yellow(self) -> None:
        self.assertEqual(self._classify(60.0), "YELLOW")

    def test_between_1_and_48gb_is_red(self) -> None:
        self.assertEqual(self._classify(20.0), "RED")

    def test_below_1gb_is_critical(self) -> None:
        self.assertEqual(self._classify(0.5), "CRITICAL")


class DiskPressureRefreshTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_refresh_caches_state(self) -> None:
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=70.0)):
            state = disk_pressure.refresh_disk_pressure_state()
        self.assertEqual(state, "GREEN")
        self.assertEqual(cache.get(disk_pressure._CACHE_KEY), "GREEN")

    def test_first_yellow_transition_emits_alert(self) -> None:
        with patch("apps.pipeline.services.disk_pressure._emit_alert") as emit:
            with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                       return_value=_fake_usage(free_gb=60.0)):
                disk_pressure.refresh_disk_pressure_state()
        self.assertEqual(emit.call_count, 1)

    def test_repeat_at_same_state_does_not_re_alert(self) -> None:
        with patch("apps.pipeline.services.disk_pressure._emit_alert") as emit:
            with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                       return_value=_fake_usage(free_gb=60.0)):
                disk_pressure.refresh_disk_pressure_state()
                disk_pressure.refresh_disk_pressure_state()
                disk_pressure.refresh_disk_pressure_state()
        self.assertEqual(emit.call_count, 1, "Repeat YELLOW ticks must not re-alert")

    def test_recovery_to_green_clears_alert_dedup(self) -> None:
        # Trip into RED.
        with patch("apps.pipeline.services.disk_pressure._emit_alert"):
            with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                       return_value=_fake_usage(free_gb=20.0)):
                disk_pressure.refresh_disk_pressure_state()
        self.assertEqual(cache.get(disk_pressure._LAST_ALERT_KEY), "RED")
        # Recover to GREEN — dedup key cleared.
        with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                   return_value=_fake_usage(free_gb=70.0)):
            disk_pressure.refresh_disk_pressure_state()
        self.assertIsNone(cache.get(disk_pressure._LAST_ALERT_KEY))
        # New trip into RED → re-alerts.
        with patch("apps.pipeline.services.disk_pressure._emit_alert") as emit:
            with patch("apps.pipeline.services.disk_pressure.shutil.disk_usage",
                       return_value=_fake_usage(free_gb=20.0)):
                disk_pressure.refresh_disk_pressure_state()
        self.assertEqual(emit.call_count, 1)
