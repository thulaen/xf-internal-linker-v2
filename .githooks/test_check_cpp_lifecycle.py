"""Tests for the C++ kernel lifecycle hook (Rule J, 2026-05-16).

Six focused cases:
  1. Empty diff -> hook passes silently
  2. New kernel with all three registrations + non-empty source + correct
     PYBIND11_MODULE -> pass
  3. New .cpp source without EXTENSION_NAMES registration -> FAIL
  4. New EXTENSION_NAMES entry without .cpp source -> FAIL
  5. 0-byte .cpp source file -> FAIL
  6. .cpp source whose PYBIND11_MODULE declares a different module name
     than the filename -> FAIL
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
    module_name = "check_cpp_lifecycle"
    path = HOOKS_DIR / "check-cpp-lifecycle.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
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


def _make_repo(tmp: Path, *, source_text: str, ensure_set: set[str], native_names: list[str]) -> None:
    """Build a synthetic repo with the three files the hook reads."""
    (tmp / "backend" / "extensions").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "apps" / "diagnostics").mkdir(parents=True, exist_ok=True)
    # Caller writes the source file via the source_text path. Empty value
    # means "do not create".
    ensure_lit = "{" + ", ".join(f'"{n}"' for n in sorted(ensure_set)) + "}"
    (tmp / "scripts" / "ensure_compiled_artifacts.py").write_text(
        f"EXTENSION_NAMES = {ensure_lit}\n",
        encoding="utf-8",
    )
    runtime_lit = "\n".join(
        f'    ("{n}", "fn", "label", False),' for n in native_names
    )
    health_text = (
        "_NATIVE_RUNTIME_MODULES = (\n"
        f"{runtime_lit}\n"
        ")\n"
    )
    (tmp / "backend" / "apps" / "diagnostics" / "health.py").write_text(
        health_text, encoding="utf-8"
    )


def _patch_repo_paths(module, tmp: Path):
    """Repoint the hook's constants at the synthetic tmp tree."""
    module.REPO_ROOT = tmp
    module.EXTENSIONS_DIR = tmp / "backend" / "extensions"
    module.ENSURE_SCRIPT = tmp / "scripts" / "ensure_compiled_artifacts.py"
    module.HEALTH_FILE = tmp / "backend" / "apps" / "diagnostics" / "health.py"


class CppLifecycleHookTests(TestCase):

    def _run_with_diff(self, tmp: Path, diff_lines: list[str]) -> tuple[int, str]:
        def fake_run(cmd, **_kwargs):
            joined = " ".join(cmd)
            if "--name-only" in joined:
                return _FakeCompleted(stdout="\n".join(diff_lines) + "\n")
            return _FakeCompleted(stdout="")
        captured = io.StringIO()
        # Patch the helpers module that the refactored hook delegates to.
        from _hook_helpers import subprocess as helpers_subprocess
        with patch.object(helpers_subprocess, "run", side_effect=fake_run), \
             patch.object(hook.sys, "stderr", captured):
            return hook.main(), captured.getvalue()

    def test_empty_diff_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set=set(), native_names=[])
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, _ = self._run_with_diff(tmp, [])
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0)

    def test_complete_registration_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set={"newkernel"}, native_names=["newkernel"])
            (tmp / "backend" / "extensions" / "newkernel.cpp").write_text(
                "#include <pybind11/pybind11.h>\n"
                "PYBIND11_MODULE(newkernel, m) { m.doc() = \"x\"; }\n",
                encoding="utf-8",
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run_with_diff(
                    tmp,
                    [
                        "backend/extensions/newkernel.cpp",
                        "scripts/ensure_compiled_artifacts.py",
                        "backend/apps/diagnostics/health.py",
                    ],
                )
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0, f"unexpected failure: {err}")

    def test_source_without_registration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set=set(), native_names=[])
            (tmp / "backend" / "extensions" / "ghost.cpp").write_text(
                "#include <pybind11/pybind11.h>\n"
                "PYBIND11_MODULE(ghost, m) {}\n",
                encoding="utf-8",
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run_with_diff(tmp, ["backend/extensions/ghost.cpp"])
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("ghost", err)
            self.assertIn("half-registered", err)
            self.assertIn("EXTENSION_NAMES", err)

    def test_registration_without_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set={"phantom"}, native_names=["phantom"])
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run_with_diff(tmp, ["scripts/ensure_compiled_artifacts.py"])
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("phantom", err)
            self.assertIn("non-empty", err)

    def test_zero_byte_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set={"empty"}, native_names=["empty"])
            (tmp / "backend" / "extensions" / "empty.cpp").write_text("", encoding="utf-8")
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run_with_diff(tmp, ["backend/extensions/empty.cpp"])
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("0 bytes", err)
            self.assertIn("empty.cpp", err)

    def test_pybind_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set={"correct"}, native_names=["correct"])
            (tmp / "backend" / "extensions" / "correct.cpp").write_text(
                "PYBIND11_MODULE(typo_module, m) {}\n",
                encoding="utf-8",
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run_with_diff(tmp, ["backend/extensions/correct.cpp"])
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("typo_module", err)
            self.assertIn("must match", err)

    def test_fail_message_is_three_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp, source_text="", ensure_set=set(), native_names=[])
            (tmp / "backend" / "extensions" / "x.cpp").write_text("PYBIND11_MODULE(x, m){}\n", encoding="utf-8")
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                _, err = self._run_with_diff(tmp, ["backend/extensions/x.cpp"])
            finally:
                _patch_repo_paths(hook, original)
            self.assertIn("FAIL check-cpp-lifecycle", err)
            self.assertIn("WHY:", err)
            self.assertIn("UNBLOCK:", err)
            self.assertIn("Rule J", err)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
