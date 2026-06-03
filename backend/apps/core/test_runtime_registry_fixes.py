"""Tests for runtime_registry.py and helper_router.py bug fixes.

Fix 2: _safe_int_setting guard so non-numeric AppSetting values don't crash
       get_active_runtime_model() with ValueError.

Fix 3: Hardware change detection uses != so downgrades are detected too,
       not only upgrades.

Fix 4: helper_router.route_task() must not raise TypeError when
       requires_warmed_models is None.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase


# ── Fix 2: _safe_int_setting ──────────────────────────────────────────────


class SafeIntSettingTests(SimpleTestCase):
    """Direct tests for the _safe_int_setting helper."""

    def _call(self, raw, default):
        from apps.core.runtime_registry import _safe_int_setting
        return _safe_int_setting(raw, default)

    def test_numeric_string_returns_int(self):
        self.assertEqual(self._call("64", 32), 64)

    def test_none_returns_default(self):
        self.assertEqual(self._call(None, 32), 32)

    def test_empty_string_returns_default(self):
        self.assertEqual(self._call("", 32), 32)

    def test_non_numeric_string_returns_default(self):
        """AutoIssue Fix 2: "abc" must not raise ValueError — must return default."""
        self.assertEqual(self._call("abc", 32), 32)

    def test_zero_string_returns_zero(self):
        self.assertEqual(self._call("0", 32), 0)

    def test_integer_input_returns_int(self):
        self.assertEqual(self._call(16, 32), 16)

    def test_float_string_truncates(self):
        self.assertEqual(self._call("12.9", 32), 12)


class GetActiveRuntimeModelBatchSizeFallbackTests(TestCase):
    """get_active_runtime_model must not raise when AppSetting holds non-numeric value."""

    def test_non_numeric_batch_size_setting_falls_back_to_32(self):
        """AutoIssue Fix 2: int("abc" or 32) raises; _safe_int_setting must handle it."""
        from apps.core.runtime_registry import get_active_runtime_model

        with patch(
            "apps.core.runtime_registry.AppSetting.objects"
        ) as mock_qs:
            # Simulate AppSetting returning a non-numeric value for batch_size
            def filter_side_effect(key=None, **kwargs):
                inner = MagicMock()
                if key == "system.embedding_batch_size":
                    inner.values_list.return_value.first.return_value = "abc"
                elif key == "embedding.model":
                    inner.first.return_value = None
                else:
                    inner.values_list.return_value.first.return_value = None
                    inner.first.return_value = None
                return inner

            mock_qs.filter.side_effect = filter_side_effect

            # Must not raise ValueError
            with patch("apps.core.runtime_registry.RuntimeModelRegistry.objects") as mock_reg:
                mock_reg.filter.return_value.exclude.return_value.order_by.return_value.first.return_value = None
                mock_reg.get_or_create.return_value = (MagicMock(role="champion", status="ready"), True)
                try:
                    get_active_runtime_model()
                except Exception as exc:
                    self.fail(
                        f"get_active_runtime_model raised {type(exc).__name__}: {exc} "
                        "when AppSetting had a non-numeric batch_size value"
                    )


# ── Fix 3: Hardware downgrade detection ──────────────────────────────────


class HardwareDowngradeDetectionTests(TestCase):
    """capture_primary_hardware_snapshot must set detected_upgrade=True on any change,
    including hardware downgrades (fewer CPUs or less RAM than the previous snapshot).
    """

    def _make_snapshot(self, cpu_cores: int, ram_gb: float):
        from apps.core.runtime_models import HardwareCapabilitySnapshot

        return HardwareCapabilitySnapshot.objects.create(
            node_kind="primary",
            cpu_cores=cpu_cores,
            ram_gb=ram_gb,
            gpu_name="",
            gpu_vram_gb=0.0,
            disk_free_gb=0.0,
            native_kernels_healthy=False,
            snapshot={"cpu_cores": cpu_cores, "ram_gb": ram_gb},
            detected_upgrade=False,
        )

    def _run_snapshot(self, cpu_cores: int, ram_total_bytes: int) -> object:
        """Call capture_primary_hardware_snapshot(force=True) with controlled hardware values."""
        from apps.core.runtime_registry import capture_primary_hardware_snapshot

        vm = MagicMock()
        vm.total = ram_total_bytes

        with (
            patch("os.cpu_count", return_value=cpu_cores),
            patch("psutil.virtual_memory", return_value=vm),
            patch("shutil.disk_usage", side_effect=OSError("no disk")),
        ):
            return capture_primary_hardware_snapshot(force=True)

    def test_hardware_downgrade_sets_detected_upgrade_true(self):
        """AutoIssue Fix 3: CPU decrease must set detected_upgrade=True."""
        self._make_snapshot(cpu_cores=16, ram_gb=32.0)
        result = self._run_snapshot(cpu_cores=8, ram_total_bytes=32 * (1024**3))
        self.assertTrue(
            result.detected_upgrade,
            "detected_upgrade must be True when CPU count decreases",
        )

    def test_ram_downgrade_sets_detected_upgrade_true(self):
        """AutoIssue Fix 3: RAM decrease must set detected_upgrade=True."""
        self._make_snapshot(cpu_cores=4, ram_gb=32.0)
        result = self._run_snapshot(cpu_cores=4, ram_total_bytes=16 * (1024**3))
        self.assertTrue(
            result.detected_upgrade,
            "detected_upgrade must be True when RAM decreases",
        )

    def test_cpu_increase_still_detected(self):
        """Existing upgrade detection must not regress after the fix."""
        self._make_snapshot(cpu_cores=4, ram_gb=16.0)
        result = self._run_snapshot(cpu_cores=8, ram_total_bytes=16 * (1024**3))
        self.assertTrue(result.detected_upgrade)

    def test_no_hardware_change_leaves_detected_upgrade_false(self):
        self._make_snapshot(cpu_cores=4, ram_gb=16.0)
        result = self._run_snapshot(cpu_cores=4, ram_total_bytes=16 * (1024**3))
        self.assertFalse(result.detected_upgrade)


# ── Fix 4: helper_router.route_task requires_warmed_models=None ─────────


class RouteTaskWarmModelNoneTests(SimpleTestCase):
    """route_task must not raise TypeError when requires_warmed_models is None."""

    def _make_constraint(self, requires_warmed_models):
        """Build a constraint-like object with the given requires_warmed_models value."""
        return SimpleNamespace(
            cpu_intensive=False,
            gpu_required=False,
            storage_writes_to="none",
            ram_peak_mb=256,
            requires_warmed_models=requires_warmed_models,
        )

    def test_route_task_does_not_crash_when_requires_warmed_models_is_none(self):
        """AutoIssue Fix 4: None is not iterable — must use (... or []) guard."""
        from apps.core.helper_router import route_task

        constraint = self._make_constraint(requires_warmed_models=None)

        with patch("apps.core.helpers.get_constraint", return_value=constraint):
            with patch("apps.core.helper_router.select_best_helper_node", return_value=None):
                try:
                    result = route_task("some.task", queue="default")
                except TypeError as exc:
                    self.fail(
                        f"route_task raised TypeError: {exc} — "
                        "requires_warmed_models=None must not crash"
                    )
                self.assertIsNone(result)

    def test_route_task_empty_tuple_works(self):
        """Sanity: empty tuple (default) must work without issues."""
        from apps.core.helper_router import route_task

        constraint = self._make_constraint(requires_warmed_models=())

        with patch("apps.core.helpers.get_constraint", return_value=constraint):
            with patch("apps.core.helper_router.select_best_helper_node", return_value=None):
                result = route_task("some.task", queue="default")
        self.assertIsNone(result)

    def test_route_task_warmed_model_key_is_added_to_required(self):
        """When requires_warmed_models=("key-a",), route_task passes warmed_model_key."""
        from apps.core.helper_router import route_task

        constraint = self._make_constraint(requires_warmed_models=("key-a",))
        captured = {}

        def capture_call(**kwargs):
            captured.update(kwargs)
            return None

        with patch("apps.core.helpers.get_constraint", return_value=constraint):
            with patch(
                "apps.core.helper_router.select_best_helper_node",
                side_effect=capture_call,
            ):
                route_task("some.task", queue="default")

        self.assertEqual(captured.get("required_capabilities", {}).get("warmed_model_key"), "key-a")
