"""Tests for the observability-pipeline gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-observability-pipeline.py")
spec = importlib.util.spec_from_file_location("check_observability_pipeline", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CheckObservabilityPipelineTests(unittest.TestCase):
    def test_passes_when_pipeline_check_runs(self) -> None:
        with patch.object(
            hook,
            "_check_pipeline",
            return_value=(True, "[OBSERVABILITY PIPELINE: window=24h silent=0/7 sources=none]"),
        ):
            self.assertEqual(hook.main(), 0)

    def test_warns_but_passes_on_silent_source(self) -> None:
        out = "[OBSERVABILITY PIPELINE: window=24h silent=2/7 sources=loki,tempo]"
        with patch.object(hook, "_check_pipeline", return_value=(True, out)), \
             patch.object(hook.sys.stdout, "write") as wout:
            self.assertEqual(hook.main(), 0)
        written = "".join(c.args[0] for c in wout.call_args_list)
        self.assertIn("WARN", written)

    def test_blocks_when_backend_unreachable(self) -> None:
        with patch.object(
            hook,
            "_check_pipeline",
            return_value=(False, "Kubernetes backend is unavailable."),
        ):
            self.assertEqual(hook.main(), 1)

    def test_check_pipeline_uses_shared_backend_runner(self) -> None:
        seen = {}

        def fake_run(command, **_kwargs):
            seen["command"] = command
            return hook.subprocess.CompletedProcess(command, 0, "ok\n", "")

        with patch.object(hook.subprocess, "run", fake_run):
            ok, output = hook._check_pipeline()

        self.assertTrue(ok)
        self.assertEqual(output, "ok")
        self.assertIn("backend_manage.py", seen["command"][1])
        self.assertNotIn("docker", seen["command"])

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail("detail")
        written = "".join(c.args[0] for c in werr.call_args_list)
        self.assertIn("FAIL check-observability-pipeline", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


if __name__ == "__main__":
    unittest.main()
