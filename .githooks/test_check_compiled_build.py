"""Tests for the compiled-build gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-compiled-build.py")
spec = importlib.util.spec_from_file_location("check_compiled_build", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class GoServiceDetectionTests(unittest.TestCase):
    def test_detects_existing_go_service(self) -> None:
        # streamd is a real service with a go.mod in the repo.
        svc = hook._go_services(["services/streamd/internal/publish.go"])
        self.assertIn("streamd", svc)

    def test_skips_generated_and_tests(self) -> None:
        svc = hook._go_services([
            "services/streamd/api/gen/x.pb.go",
            "services/streamd/internal/x_test.go",
        ])
        self.assertEqual(svc, [])

    def test_ignores_service_without_go_mod(self) -> None:
        svc = hook._go_services(["services/does_not_exist/main.go"])
        self.assertEqual(svc, [])


class CppDetectionTests(unittest.TestCase):
    def test_detects_cpp(self) -> None:
        self.assertTrue(hook._has_cpp(["backend/extensions/scoring.cpp"]))

    def test_ignores_cpp_tests(self) -> None:
        self.assertFalse(hook._has_cpp(["backend/extensions/tests/test_x.cpp"]))


class MainTests(unittest.TestCase):
    def test_no_staged_passes(self) -> None:
        with patch.object(hook, "_staged", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_go_build_failure_blocks(self) -> None:
        with patch.object(hook, "_staged",
                          return_value=["services/streamd/internal/x.go"]), \
             patch.object(hook, "_go_services", return_value=["streamd"]), \
             patch.object(hook, "_build_go", return_value="boom"), \
             patch.object(hook, "_has_cpp", return_value=False):
            self.assertEqual(hook.main(), 1)

    def test_go_build_success_passes(self) -> None:
        with patch.object(hook, "_staged",
                          return_value=["services/streamd/internal/x.go"]), \
             patch.object(hook, "_go_services", return_value=["streamd"]), \
             patch.object(hook, "_build_go", return_value=None), \
             patch.object(hook, "_has_cpp", return_value=False):
            self.assertEqual(hook.main(), 0)

    def test_cpp_build_failure_blocks(self) -> None:
        with patch.object(hook, "_staged",
                          return_value=["backend/extensions/scoring.cpp"]), \
             patch.object(hook, "_go_services", return_value=[]), \
             patch.object(hook, "_has_cpp", return_value=True), \
             patch.object(hook, "_build_cpp", return_value="cpp boom"):
            self.assertEqual(hook.main(), 1)

    def test_docker_missing_reports_failure(self) -> None:
        with patch.object(hook.subprocess, "run", side_effect=FileNotFoundError):
            code, out = hook._docker_exec("compiled-tools", "x", 10)
            self.assertEqual(code, 1)
            self.assertIn("Docker is not available", out)

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail("detail")
        written = "".join(c.args[0] for c in werr.call_args_list)
        self.assertIn("FAIL check-compiled-build", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


if __name__ == "__main__":
    unittest.main()
