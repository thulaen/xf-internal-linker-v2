"""Tests for scripts/tdd_write_guard.py.

BDD:
  Given a production source file with no matching test
  When main() processes the Write payload
  Then it returns exit code 2 (blocked)

  Given an exempt extension (.yml/.md/.json) or a test file
  When _is_exempt() runs
  Then it returns True (always allowed)
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "tdd_write_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("tdd_write_guard", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tdd_write_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


g = _load()


class TestIsExempt(TestCase):
    def test_yaml_is_exempt(self) -> None:
        self.assertTrue(g._is_exempt("config/app.yml"))
        self.assertTrue(g._is_exempt("config/app.yaml"))

    def test_markdown_and_json_exempt(self) -> None:
        self.assertTrue(g._is_exempt("README.md"))
        self.assertTrue(g._is_exempt("package.json"))

    def test_dockerfile_exempt(self) -> None:
        self.assertTrue(g._is_exempt("backend/Dockerfile"))
        self.assertTrue(g._is_exempt("backend/Dockerfile.prod"))

    def test_test_prefix_file_exempt(self) -> None:
        self.assertTrue(g._is_exempt("scripts/test_foo.py"))

    def test_under_tests_dir_exempt(self) -> None:
        self.assertTrue(g._is_exempt("backend/apps/audit/tests/helpers.py"))

    def test_docs_fragment_exempt(self) -> None:
        self.assertTrue(g._is_exempt("docs/specs/foo.py"))

    def test_plain_python_source_not_exempt(self) -> None:
        self.assertFalse(g._is_exempt("scripts/foo.py"))

    def test_shell_source_not_exempt(self) -> None:
        self.assertFalse(g._is_exempt("scripts/deploy.sh"))


class TestCandidateTestFiles(TestCase):
    def test_includes_test_prefixed_sibling(self) -> None:
        cands = g._candidate_test_files("scripts/foo.py")
        names = {c.name for c in cands}
        self.assertIn("test_foo.py", names)

    def test_includes_scripts_tests_location(self) -> None:
        cands = g._candidate_test_files("scripts/foo.py")
        as_posix = {c.as_posix() for c in cands}
        self.assertTrue(
            any(p.endswith("scripts/tests/test_foo.py") for p in as_posix)
        )


class TestMain(TestCase):
    def _run_with_payload(self, payload: dict) -> int:
        stdin = io.StringIO(json.dumps(payload))
        with mock.patch.object(g.sys, "stdin", stdin), mock.patch.object(
            g.sys, "stderr", io.StringIO()
        ):
            return g.main()

    def test_allows_when_no_path(self) -> None:
        self.assertEqual(self._run_with_payload({"tool_input": {}}), 0)

    def test_allows_exempt_file(self) -> None:
        self.assertEqual(
            self._run_with_payload({"tool_input": {"file_path": "a.yml"}}), 0
        )

    def test_allows_when_candidate_test_exists(self) -> None:
        with mock.patch.object(g.Path, "exists", return_value=True):
            rc = self._run_with_payload(
                {"tool_input": {"file_path": "scripts/foo.py"}}
            )
        self.assertEqual(rc, 0)

    def test_blocks_with_exit_2_when_no_test(self) -> None:
        with mock.patch.object(g.Path, "exists", return_value=False):
            rc = self._run_with_payload(
                {"tool_input": {"file_path": "scripts/foo.py"}}
            )
        self.assertEqual(rc, 2)
