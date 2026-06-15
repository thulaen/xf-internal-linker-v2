"""Convention-named SimpleTestCase coverage for apps/core/views_runtime.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in views_runtime.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import views_runtime


class ViewsRuntimeConstantLiteralTests(SimpleTestCase):
    def test_bytes_per_megabyte_is_1048576(self) -> None:
        self.assertEqual(views_runtime._BYTES_PER_MEGABYTE, 1048576)

    def test_runtime_settings_keys_exact(self) -> None:
        self.assertEqual(
            views_runtime._RUNTIME_SETTINGS_KEYS,
            (
                "system.runtime_mode",
                "system.performance_mode",
                "system.performance_mode_expiry",
                "system.performance_mode_expires_at",
                "system.master_pause",
            ),
        )

    def test_performance_mode_choices_exact(self) -> None:
        self.assertEqual(
            views_runtime._PERFORMANCE_MODE_CHOICES, ("safe", "balanced", "high")
        )

    def test_performance_expiry_choices_exact(self) -> None:
        self.assertEqual(
            views_runtime._PERFORMANCE_EXPIRY_CHOICES, ("none", "activity", "night")
        )


class RuntimeConfigConstantLiteralTests(SimpleTestCase):
    def test_batch_size_limits_are_8_and_128(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.BATCH_SIZE_MIN, 8)
        self.assertEqual(views_runtime.RuntimeConfigView.BATCH_SIZE_MAX, 128)

    def test_queue_concurrency_limits_are_1_and_6(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.DEFAULT_QUEUE_CONCURRENCY_MIN, 1)
        self.assertEqual(views_runtime.RuntimeConfigView.DEFAULT_QUEUE_CONCURRENCY_MAX, 6)

    def test_cpu_thread_default_is_4(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.CPU_THREAD_DEFAULT, 4)


class ResolvePerformanceExpiryChoiceTests(SimpleTestCase):
    def test_non_high_mode_forces_none(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="safe", raw_expiry="night"), 
            "none"
        )

    def test_invalid_expiry_forces_none(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="high", raw_expiry="invalid"), 
            "none"
        )

    def test_valid_expiry(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="high", raw_expiry="night"),
            "night"
        )


class RuntimeConfigSnapshotGpuFieldTests(SimpleTestCase):
    """The runtime-config snapshot must expose the new GPU memory + temperature
    fields, their derived defaults, and their valid ranges.

    These tests pin the behaviour added when the GPU budget/temperature
    tunables were introduced. They mock the DB-reading helpers so no database
    is touched (matching the rest of this SimpleTestCase module)."""

    def _build_view(self):
        view = views_runtime.RuntimeConfigView()
        # Make the DB readers echo the supplied default so the snapshot reflects
        # the django-conf-derived defaults rather than any stored override.
        view._read_int = MagicMock(side_effect=lambda key, default: default)
        view._read_bool = MagicMock(side_effect=lambda key, default: default)
        view._cpu_thread_cap = MagicMock(return_value=8)
        view._default_queue_concurrency = MagicMock(return_value=2)
        return view

    def test_snapshot_exposes_gpu_fields_and_ranges(self) -> None:
        view = self._build_view()
        fake_conf = MagicMock()
        fake_conf.EMBEDDING_BATCH_SIZE = 32
        fake_conf.GPU_MEMORY_FRACTION_HIGH = 0.8
        fake_conf.GPU_TEMP_CEILING_C = 90
        with patch("django.conf.settings", fake_conf):
            snapshot = view._runtime_config_snapshot()

        # Derived defaults: 0.8 fraction -> 80 percent; ceiling 90 -> 90 C.
        self.assertEqual(snapshot["gpu_memory_budget_pct"], 80)
        self.assertEqual(snapshot["gpu_temp_pause_c"], 90)
        # Ranges advertised to the UI.
        self.assertEqual(snapshot["gpu_memory_budget_pct_range"], [10, 95])
        self.assertEqual(snapshot["gpu_temp_pause_c_range"], [50, 95])

    def test_snapshot_gpu_defaults_track_django_conf(self) -> None:
        view = self._build_view()
        fake_conf = MagicMock()
        fake_conf.EMBEDDING_BATCH_SIZE = 32
        fake_conf.GPU_MEMORY_FRACTION_HIGH = 0.5
        fake_conf.GPU_TEMP_CEILING_C = 75
        with patch("django.conf.settings", fake_conf):
            snapshot = view._runtime_config_snapshot()

        # 0.5 fraction -> 50 percent; ceiling 75 -> 75 C. Proves the default
        # computation reads the settings rather than a hardcoded literal.
        self.assertEqual(snapshot["gpu_memory_budget_pct"], 50)
        self.assertEqual(snapshot["gpu_temp_pause_c"], 75)


class RuntimeConfigGpuFieldSpecTests(SimpleTestCase):
    """The int-field spec table must include the two GPU fields with the exact
    DB keys and bounds the validator enforces."""

    def test_int_field_specs_include_gpu_entries(self) -> None:
        view = views_runtime.RuntimeConfigView()
        view._cpu_thread_cap = MagicMock(return_value=8)
        specs = {spec["field"]: spec for spec in view._int_field_specs()}

        self.assertIn("gpu_memory_budget_pct", specs)
        self.assertEqual(
            specs["gpu_memory_budget_pct"]["db_key"], "system.gpu_memory_budget_pct"
        )
        self.assertEqual(specs["gpu_memory_budget_pct"]["lo"], 10)
        self.assertEqual(specs["gpu_memory_budget_pct"]["hi"], 95)

        self.assertIn("gpu_temp_pause_c", specs)
        self.assertEqual(
            specs["gpu_temp_pause_c"]["db_key"], "system.gpu_temp_pause_c"
        )
        self.assertEqual(specs["gpu_temp_pause_c"]["lo"], 50)
        self.assertEqual(specs["gpu_temp_pause_c"]["hi"], 95)

    def test_gpu_memory_pct_rejects_out_of_range_value(self) -> None:
        view = views_runtime.RuntimeConfigView()
        view._cpu_thread_cap = MagicMock(return_value=8)
        view._upsert_setting = MagicMock()
        spec = next(
            s for s in view._int_field_specs() if s["field"] == "gpu_memory_budget_pct"
        )
        updated: dict = {}
        errors: dict = {}
        view._apply_int_range_setting(
            data={"gpu_memory_budget_pct": 99}, spec=spec, updated=updated, errors=errors
        )
        # 99 is above the hi=95 bound, so it must be rejected and never upserted.
        self.assertIn("gpu_memory_budget_pct", errors)
        self.assertEqual(errors["gpu_memory_budget_pct"], "Must be between 10 and 95.")
        view._upsert_setting.assert_not_called()
        self.assertNotIn("gpu_memory_budget_pct", updated)

    def test_gpu_temp_pause_accepts_in_range_value(self) -> None:
        view = views_runtime.RuntimeConfigView()
        view._cpu_thread_cap = MagicMock(return_value=8)
        view._upsert_setting = MagicMock()
        spec = next(
            s for s in view._int_field_specs() if s["field"] == "gpu_temp_pause_c"
        )
        updated: dict = {}
        errors: dict = {}
        view._apply_int_range_setting(
            data={"gpu_temp_pause_c": 70}, spec=spec, updated=updated, errors=errors
        )
        # 70 is inside [50, 95], so it must be persisted with the right DB key.
        self.assertEqual(updated["gpu_temp_pause_c"], 70)
        self.assertNotIn("gpu_temp_pause_c", errors)
        view._upsert_setting.assert_called_once_with(
            key="system.gpu_temp_pause_c", value=70
        )
