"""Unit tests for check-always-on-quota.py pure logic."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_HOOK = Path(__file__).resolve().parent / "check-always-on-quota.py"
_spec = importlib.util.spec_from_file_location("check_always_on_quota", _HOOK)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class VerifyCmdTests(unittest.TestCase):
    def test_cmd_includes_source_and_threshold(self):
        cmd = mod._verify_cmd("prometheus", 10, None)
        self.assertIn("backend_manage.py", cmd[1])
        self.assertIn("verify_always_on_quota", cmd)
        self.assertIn("prometheus", cmd)
        self.assertIn("10", cmd)
        self.assertNotIn("--resolved-after", cmd)
        self.assertNotIn("docker", cmd)

    def test_cmd_adds_cutoff_when_present(self):
        cmd = mod._verify_cmd("prometheus", 10, "2026-05-30 06:00")
        self.assertIn("--resolved-after", cmd)
        self.assertIn("2026-05-30 06:00", cmd)

    def test_prometheus_is_configured_at_ten(self):
        self.assertIn(("prometheus", 10), mod.ALWAYS_ON_SOURCES)

    def test_rust_compiler_is_configured_at_ten(self):
        self.assertIn(("rust_compiler", 10), mod.ALWAYS_ON_SOURCES)
        self.assertNotIn(("compiler", 10), mod.ALWAYS_ON_SOURCES)


class MainTests(unittest.TestCase):
    def test_no_staged_files_passes(self):
        with patch.object(mod, "_staged_files", return_value=[]):
            self.assertEqual(mod.main(), 0)

    def test_passes_when_verify_returns_zero(self):
        with (
            patch.object(mod, "_staged_files", return_value=["a.py"]),
            patch.object(mod, "_cutoff_stamp", return_value=None),
            patch.object(mod, "_run", return_value=(0, "ok")),
        ):
            self.assertEqual(mod.main(), 0)

    def test_blocks_when_verify_fails(self):
        with (
            patch.object(mod, "_staged_files", return_value=["a.py"]),
            patch.object(mod, "_cutoff_stamp", return_value=None),
            patch.object(mod, "_run", return_value=(1, "resolve 3 more")),
        ):
            self.assertEqual(mod.main(), 1)

    def test_backend_helper_missing_blocks(self):
        with (
            patch.object(mod, "_staged_files", return_value=["a.py"]),
            patch.object(mod, "_cutoff_stamp", return_value=None),
            patch.object(mod, "_run", return_value=(2, "Backend helper is not available.")),
        ):
            self.assertEqual(mod.main(), 1)


if __name__ == "__main__":
    unittest.main()
