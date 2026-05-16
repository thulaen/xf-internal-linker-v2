"""Tests for the C++ kernel lifecycle hook (Rule J, full-tree mode 2026-05-16).

Seven focused cases:
  1. Clean three-way alignment (source + EXTENSION_NAMES + _NATIVE_RUNTIME_MODULES) -> pass
  2. Empty repo skeleton (no extensions dir) -> pass
  3. New .cpp source without EXTENSION_NAMES + runtime registration -> FAIL
  4. EXTENSION_NAMES entry without .cpp source -> FAIL
  5. _NATIVE_RUNTIME_MODULES entry without .cpp source -> FAIL
  6. 0-byte .cpp source file -> FAIL
  7. PYBIND11_MODULE name disagrees with filename stem -> FAIL
  8. FAIL message is Rule-F three-part (FAIL: / WHY: / UNBLOCK:)
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


def _make_repo(
    tmp: Path,
    *,
    sources: dict[str, str],
    ensure_set: set[str],
    runtime_names: list[str],
) -> None:
    """Build a synthetic repo tree mirroring the three lifecycle files."""
    (tmp / "backend" / "extensions").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "apps" / "diagnostics").mkdir(parents=True, exist_ok=True)

    for name, body in sources.items():
        (tmp / "backend" / "extensions" / f"{name}.cpp").write_text(body, encoding="utf-8")

    ensure_lit = "{" + ", ".join(f'"{n}"' for n in sorted(ensure_set)) + "}"
    (tmp / "scripts" / "ensure_compiled_artifacts.py").write_text(
        f"EXTENSION_NAMES = {ensure_lit}\n",
        encoding="utf-8",
    )

    runtime_lit = "\n".join(
        f'    ("{n}", "fn", "label", False),' for n in runtime_names
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
    module.REPO_ROOT = tmp
    module.EXTENSIONS_DIR = tmp / "backend" / "extensions"
    module.ENSURE_SCRIPT = tmp / "scripts" / "ensure_compiled_artifacts.py"
    module.HEALTH_FILE = tmp / "backend" / "apps" / "diagnostics" / "health.py"


def _good_pybind(name: str) -> str:
    return (
        "#include <pybind11/pybind11.h>\n"
        f"PYBIND11_MODULE({name}, m) {{ m.doc() = \"x\"; }}\n"
    )


class CppLifecycleFullTreeTests(TestCase):

    def _run(self, tmp: Path) -> tuple[int, str]:
        captured = io.StringIO()
        with patch.object(hook.sys, "stderr", captured):
            return hook.main(), captured.getvalue()

    def test_clean_three_way_alignment_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"alpha": _good_pybind("alpha"), "beta": _good_pybind("beta")},
                ensure_set={"alpha", "beta"},
                runtime_names=["alpha", "beta"],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0, err)

    def test_missing_skeleton_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, _ = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0)

    def test_source_without_registration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"ghost": _good_pybind("ghost")},
                ensure_set=set(),
                runtime_names=[],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("ghost", err)
            self.assertIn("half-registered", err)
            self.assertIn("EXTENSION_NAMES", err)
            self.assertIn("_NATIVE_RUNTIME_MODULES", err)

    def test_extension_names_without_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={},
                ensure_set={"phantom"},
                runtime_names=[],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("phantom", err)
            self.assertIn("non-empty", err)

    def test_runtime_only_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={},
                ensure_set=set(),
                runtime_names=["runtime_only"],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("runtime_only", err)
            self.assertIn("half-registered", err)

    def test_zero_byte_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"empty": ""},
                ensure_set={"empty"},
                runtime_names=["empty"],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("0 bytes", err)
            self.assertIn("empty.cpp", err)

    def test_pybind_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"correct": "PYBIND11_MODULE(typo_module, m) {}\n"},
                ensure_set={"correct"},
                runtime_names=["correct"],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("typo_module", err)
            self.assertIn("must match", err)

    def test_fail_message_is_three_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"x": _good_pybind("x")},
                ensure_set=set(),
                runtime_names=[],
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                _, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertIn("FAIL check-cpp-lifecycle", err)
            self.assertIn("WHY:", err)
            self.assertIn("UNBLOCK:", err)
            self.assertIn("Rule J", err)
            self.assertIn("full-tree", err)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
