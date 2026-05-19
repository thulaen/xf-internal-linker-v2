"""Tests for .githooks/check-go-service-resource-budget.py (slice 1.6)."""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    hook_path = HOOKS_DIR / "check-go-service-resource-budget.py"
    spec = importlib.util.spec_from_file_location("check_resource_budget", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_resource_budget"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


VALID_BUDGET = {
    "host": {
        "total_memory_mb": 512,
        "total_storage_mb": 1024,
        "retention_hours": 168,
        "max_image_size_mb": 35,
        "socket_path": "/var/run/xf-sidecars/sidecars.sock",
        "storage_path": "/var/lib/xf/sidecars",
        "metrics_port": 6061,
        "idle_release_seconds": 30,
        "pruner_interval_seconds": 60,
        "memory_pressure_threshold_percent": 80,
    }
}


class ValidateTests(TestCase):
    def test_valid_budget_passes(self) -> None:
        self.assertEqual(hook.validate(VALID_BUDGET), [])

    def test_missing_host_block_fails(self) -> None:
        violations = hook.validate({"services": []})
        self.assertEqual(len(violations), 1)
        self.assertIn("host:", violations[0])

    def test_wrong_memory_cap_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], total_memory_mb=1024)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("total_memory_mb", violations[0])
        self.assertIn("512", violations[0])

    def test_wrong_storage_cap_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], total_storage_mb=4096)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("total_storage_mb", violations[0])

    def test_wrong_retention_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], retention_hours=24)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("retention_hours", violations[0])

    def test_max_image_size_over_35_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], max_image_size_mb=100)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("max_image_size_mb", violations[0])

    def test_max_image_size_zero_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], max_image_size_mb=0)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)

    def test_socket_path_outside_var_run_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], socket_path="/tmp/sidecars.sock")}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("socket_path", violations[0])

    def test_storage_path_outside_var_lib_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], storage_path="/tmp/sidecars")}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)
        self.assertIn("storage_path", violations[0])

    def test_pressure_threshold_too_low_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], memory_pressure_threshold_percent=10)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)

    def test_pressure_threshold_too_high_fails(self) -> None:
        bad = {"host": dict(VALID_BUDGET["host"], memory_pressure_threshold_percent=99)}
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 1)

    def test_multiple_violations_all_reported(self) -> None:
        bad = {
            "host": dict(
                VALID_BUDGET["host"],
                total_memory_mb=2048,
                total_storage_mb=4096,
                retention_hours=24,
            )
        }
        violations = hook.validate(bad)
        self.assertEqual(len(violations), 3)

    def test_missing_required_key_fails(self) -> None:
        bad_host = dict(VALID_BUDGET["host"])
        del bad_host["socket_path"]
        violations = hook.validate({"host": bad_host})
        self.assertEqual(len(violations), 1)
        self.assertIn("socket_path", violations[0])
        self.assertIn("missing", violations[0])


class LiveBudgetTests(TestCase):
    """Validate the actual services/sidecars/budget.yaml shipped with the slice."""

    def test_live_budget_passes_validate(self) -> None:
        if not hook.BUDGET_PATH.is_file():  # pragma: no cover
            self.skipTest("budget.yaml not present in this checkout")
        import yaml  # type: ignore[import-not-found]
        with hook.BUDGET_PATH.open(encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        self.assertEqual(hook.validate(data), [],
                         msg="services/sidecars/budget.yaml must satisfy the 7 hard constraints")


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


class MainTests(TestCase):
    def test_main_with_live_file_returns_zero(self) -> None:
        if not hook.BUDGET_PATH.is_file():  # pragma: no cover
            self.skipTest("budget.yaml not present in this checkout")
        rv, err = _capture_stderr(hook.main)
        self.assertEqual(rv, 0, msg=err)

    def test_main_with_missing_file_returns_two(self) -> None:
        original = hook.BUDGET_PATH
        try:
            hook.BUDGET_PATH = Path("/no/such/path/budget.yaml")  # type: ignore[assignment]
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 2)
            self.assertIn("budget.yaml", err)
            self.assertIn("missing", err)
        finally:
            hook.BUDGET_PATH = original  # type: ignore[assignment]

    def test_main_with_bad_yaml_returns_two(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("not: [valid: yaml")  # malformed
            tmp = Path(fp.name)
        original = hook.BUDGET_PATH
        try:
            hook.BUDGET_PATH = tmp  # type: ignore[assignment]
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 2)
            self.assertIn("budget.yaml", err)
        finally:
            hook.BUDGET_PATH = original  # type: ignore[assignment]
            tmp.unlink(missing_ok=True)

    def test_main_with_violation_reports_each_one(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(
                "host:\n"
                "  total_memory_mb: 2048\n"
                "  total_storage_mb: 1024\n"
                "  retention_hours: 168\n"
                "  max_image_size_mb: 35\n"
                "  socket_path: /var/run/xf/x.sock\n"
                "  storage_path: /var/lib/xf\n"
                "  memory_pressure_threshold_percent: 80\n"
            )
            tmp = Path(fp.name)
        original = hook.BUDGET_PATH
        try:
            hook.BUDGET_PATH = tmp  # type: ignore[assignment]
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 2)
            self.assertIn("total_memory_mb", err)
            self.assertIn("WHY:", err)
            self.assertIn("UNBLOCK:", err)
        finally:
            hook.BUDGET_PATH = original  # type: ignore[assignment]
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
