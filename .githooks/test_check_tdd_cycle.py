"""Tests for the tightened TDD cycle hook (Patch A, 2026-05-16).

Replaces the older 3-test file with a focused regression suite for the
per-file enforcement that landed in this patch:

  1. No staged source files -> hook passes silently (exit 0)
  2. Source file without ANY marker -> three-part FAIL
  3. One staged source + one matching marker -> pass
  4. Two staged sources + marker covering only one -> FAIL naming the gap
  5. Five staged sources + five matching markers -> pass
  6. Test files are NOT counted as production source
  7. .sh scripts and other non-source suffixes are dropped
  8. Generated stubs (_pb2.py, .pb.go) are NOT counted
  9. Files with `# ruff: noqa` first line are exempt
 10. Quoted file= argument is accepted by the regex
 11. FAIL message contains "WHY:" + "UNBLOCK:" + "Rule B" + "--no-verify"
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    module_name = "check_tdd_cycle"
    path = HOOKS_DIR / "check-tdd-cycle.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _make_fake_subprocess(name_only_stdout: str, handoff_diff_stdout: str):
    def side_effect(cmd, **_kwargs):
        joined = " ".join(cmd)
        if "--name-only" in joined:
            return _FakeCompleted(stdout=name_only_stdout)
        if "AGENT-HANDOFF.md" in joined:
            return _FakeCompleted(stdout=handoff_diff_stdout)
        return _FakeCompleted(stdout="")
    return side_effect


class TDDCycleHookTests(TestCase):

    def test_no_staged_source_files_passes(self) -> None:
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess("", "")):
            self.assertEqual(hook.main(), 0)

    def test_source_without_marker_fails_three_part(self) -> None:
        name_only = "backend/apps/realtime/x.py\n"
        captured = io.StringIO()
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, "no markers here")), \
             patch.object(hook.sys, "stderr", captured):
            rc = hook.main()
        self.assertEqual(rc, 2)
        text = captured.getvalue()
        self.assertIn("FAIL check-tdd-cycle", text)
        self.assertIn("WHY:", text)
        self.assertIn("UNBLOCK:", text)
        self.assertIn("Rule B", text)
        self.assertIn("--no-verify", text)

    def test_single_source_with_matching_marker_passes(self) -> None:
        name_only = "backend/apps/realtime/client.py\n"
        handoff = (
            "+[TDD CYCLE: file=backend/apps/realtime/client.py "
            "red=tests_client.py:43 green=client.py:1 refactor=\"x\"]\n"
        )
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, handoff)):
            self.assertEqual(hook.main(), 0)

    def test_partial_coverage_fails_and_names_uncovered_file(self) -> None:
        name_only = (
            "backend/apps/realtime/client.py\n"
            "backend/apps/realtime/extra.py\n"
        )
        handoff = (
            "+[TDD CYCLE: file=backend/apps/realtime/client.py "
            "red=t:1 green=s:1 refactor=\"x\"]\n"
        )
        captured = io.StringIO()
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, handoff)), \
             patch.object(hook.sys, "stderr", captured):
            rc = hook.main()
        self.assertEqual(rc, 2)
        text = captured.getvalue()
        self.assertIn("backend/apps/realtime/extra.py", text)

    def test_five_files_with_five_markers_passes(self) -> None:
        files = [f"backend/apps/realtime/file{i}.py" for i in range(5)]
        name_only = "\n".join(files) + "\n"
        handoff = "\n".join(
            f"+[TDD CYCLE: file={f} red=t:1 green=s:1 refactor=\"x\"]" for f in files
        ) + "\n"
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, handoff)):
            self.assertEqual(hook.main(), 0)

    def test_test_files_are_exempt(self) -> None:
        name_only = (
            "backend/apps/realtime/tests_streamd_client.py\n"
            "backend/apps/realtime/test_other.py\n"
            ".githooks/test_check_tdd_cycle.py\n"
            "services/streamd/test/integration/foo_test.go\n"
        )
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, "")):
            self.assertEqual(hook.main(), 0)

    def test_shell_scripts_are_not_source(self) -> None:
        name_only = (
            "scripts/run-go-vet.sh\n"
            "scripts/run-go-tests.sh\n"
        )
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, "")):
            self.assertEqual(hook.main(), 0)

    def test_generated_protobuf_stubs_are_exempt(self) -> None:
        name_only = (
            "backend/apps/realtime/_streamd_pb2/api_pb2.py\n"
            "backend/apps/realtime/_streamd_pb2/api_pb2_grpc.py\n"
            "services/streamd/api/gen/api.pb.go\n"
            "services/streamd/api/gen/api_grpc.pb.go\n"
        )
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, "")):
            self.assertEqual(hook.main(), 0)

    def test_ruff_noqa_header_exempts_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            target = tmp_root / "backend" / "apps" / "x" / "gen.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "# ruff: noqa\nclass GenStub:\n    pass\n",
                encoding="utf-8",
            )
            original_root = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = tmp_root  # type: ignore[assignment]
                name_only = "backend/apps/x/gen.py\n"
                with patch.object(
                    hook.subprocess, "run",
                    side_effect=_make_fake_subprocess(name_only, ""),
                ):
                    self.assertEqual(hook.main(), 0)
            finally:
                hook.REPO_ROOT = original_root  # type: ignore[assignment]

    def test_quoted_file_argument_in_marker_is_accepted(self) -> None:
        name_only = "backend/apps/realtime/client.py\n"
        handoff = (
            "+[TDD CYCLE: file=\"backend/apps/realtime/client.py\" "
            "red=t:1 green=s:1 refactor=\"x\"]\n"
        )
        with patch.object(hook.subprocess, "run", side_effect=_make_fake_subprocess(name_only, handoff)):
            self.assertEqual(hook.main(), 0)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
