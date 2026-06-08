"""Tests for the native kernel lifecycle hook (Rule J, full-tree mode 2026-05-16).

C++ cases:
  1. Clean three-way alignment (source + EXTENSION_NAMES + _NATIVE_RUNTIME_MODULES) -> pass
  2. Empty repo skeleton (no extensions dir) -> pass
  3. New .cpp source without EXTENSION_NAMES + runtime registration -> FAIL
  4. EXTENSION_NAMES entry without .cpp source -> FAIL
  5. _NATIVE_RUNTIME_MODULES entry without .cpp source -> FAIL
  6. 0-byte .cpp source file -> FAIL
  7. PYBIND11_MODULE name disagrees with filename stem -> FAIL
  8. FAIL message is Rule-F three-part (FAIL: / WHY: / UNBLOCK:)

Rust-port cases (2026-06-06, l2norm port):
  9.  Clean Rust three-way alignment (lib.rs + RUST_EXTENSION_NAMES +
      _NATIVE_RUNTIME_MODULES, no .cpp twin) -> pass
  10. Rust runtime kernel with no crate / no RUST_EXTENSION_NAMES -> FAIL
  11. Rust crate + RUST_EXTENSION_NAMES but missing from runtime -> FAIL
  12. #[pymodule] name disagrees with crate name -> FAIL
  13. Kernel registered as BOTH C++ and Rust (half-deleted port) -> FAIL
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
    rust_sources: dict[str, str] | None = None,
    rust_set: set[str] | None = None,
) -> None:
    """Build a synthetic repo tree mirroring the lifecycle files.

    ``rust_sources`` maps a kernel name to the body of its
    ``rust/extensions/<name>/src/lib.rs``; ``rust_set`` is the
    ``RUST_EXTENSION_NAMES`` set written into the synthetic
    ``ensure_compiled_artifacts.py``.
    """
    rust_sources = rust_sources or {}
    rust_set = rust_set or set()
    (tmp / "backend" / "extensions").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "apps" / "diagnostics").mkdir(parents=True, exist_ok=True)

    for name, body in sources.items():
        (tmp / "backend" / "extensions" / f"{name}.cpp").write_text(body, encoding="utf-8")

    for name, body in rust_sources.items():
        crate_src = tmp / "rust" / "extensions" / name / "src"
        crate_src.mkdir(parents=True, exist_ok=True)
        (crate_src / "lib.rs").write_text(body, encoding="utf-8")

    ensure_lit = "{" + ", ".join(f'"{n}"' for n in sorted(ensure_set)) + "}"
    rust_lit = "{" + ", ".join(f'"{n}"' for n in sorted(rust_set)) + "}"
    (tmp / "scripts" / "ensure_compiled_artifacts.py").write_text(
        f"EXTENSION_NAMES = {ensure_lit}\nRUST_EXTENSION_NAMES = {rust_lit}\n",
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
    module.RUST_EXTENSIONS_DIR = tmp / "rust" / "extensions"
    module.ENSURE_SCRIPT = tmp / "scripts" / "ensure_compiled_artifacts.py"
    module.HEALTH_FILE = tmp / "backend" / "apps" / "diagnostics" / "health.py"


def _good_pybind(name: str) -> str:
    return (
        "#include <pybind11/pybind11.h>\n"
        f"PYBIND11_MODULE({name}, m) {{ m.doc() = \"x\"; }}\n"
    )


def _good_pymodule(name: str) -> str:
    return (
        "use pyo3::prelude::*;\n"
        "#[pymodule]\n"
        f"fn {name}(m: &Bound<'_, PyModule>) -> PyResult<()> {{ Ok(()) }}\n"
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

    # ── Rust-port lifecycle (l2norm pattern) ──────────────────────────

    def test_clean_rust_three_way_alignment_passes(self) -> None:
        # A Rust kernel backed by lib.rs + RUST_EXTENSION_NAMES +
        # _NATIVE_RUNTIME_MODULES (and NO .cpp twin) is valid.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"scoring": _good_pybind("scoring")},
                ensure_set={"scoring"},
                runtime_names=["scoring", "l2norm"],
                rust_sources={"l2norm": _good_pymodule("l2norm")},
                rust_set={"l2norm"},
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0, err)

    def test_rust_runtime_only_without_crate_fails(self) -> None:
        # In _NATIVE_RUNTIME_MODULES but no crate and not in RUST_EXTENSION_NAMES.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={},
                ensure_set=set(),
                runtime_names=["l2norm"],
                rust_sources={},
                rust_set=set(),
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("l2norm", err)
            self.assertIn("half-registered", err)

    def test_rust_crate_missing_from_runtime_fails(self) -> None:
        # Crate + RUST_EXTENSION_NAMES but absent from _NATIVE_RUNTIME_MODULES.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={},
                ensure_set=set(),
                runtime_names=[],
                rust_sources={"l2norm": _good_pymodule("l2norm")},
                rust_set={"l2norm"},
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("l2norm", err)
            self.assertIn("_NATIVE_RUNTIME_MODULES", err)

    def test_rust_pymodule_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={},
                ensure_set=set(),
                runtime_names=["l2norm"],
                rust_sources={"l2norm": _good_pymodule("wrong_name")},
                rust_set={"l2norm"},
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("wrong_name", err)
            self.assertIn("must match", err)

    def test_kernel_registered_as_both_cpp_and_rust_fails(self) -> None:
        # Half-deleted port: l2norm still has a .cpp + EXTENSION_NAMES AND a Rust
        # crate + RUST_EXTENSION_NAMES. The C++ side was not retired.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"l2norm": _good_pybind("l2norm")},
                ensure_set={"l2norm"},
                runtime_names=["l2norm"],
                rust_sources={"l2norm": _good_pymodule("l2norm")},
                rust_set={"l2norm"},
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 2)
            self.assertIn("l2norm", err)
            self.assertIn("BOTH", err)

    def test_bare_rust_extensions_crate_without_registration_fails(self) -> None:
        # Every crate under rust/extensions/ is a kernel crate. One with a
        # lib.rs but no RUST_EXTENSION_NAMES / runtime entry is half-registered.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"scoring": _good_pybind("scoring")},
                ensure_set={"scoring"},
                runtime_names=["scoring"],
                rust_sources={"ghost": _good_pymodule("ghost")},
                rust_set=set(),
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
            self.assertIn("RUST_EXTENSION_NAMES", err)

    def test_scaffold_crate_outside_extensions_dir_is_not_scanned(self) -> None:
        # The `xf_kernels` scaffold lives at rust/xf_kernels, NOT
        # rust/extensions/, so _rust_source_kernels() never sees it and it
        # cannot trip the hook.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(
                tmp,
                sources={"scoring": _good_pybind("scoring")},
                ensure_set={"scoring"},
                runtime_names=["scoring"],
                rust_sources={},
                rust_set=set(),
            )
            scaffold_src = tmp / "rust" / "xf_kernels" / "src"
            scaffold_src.mkdir(parents=True, exist_ok=True)
            (scaffold_src / "lib.rs").write_text(
                "// scaffold crate, not a kernel\n", encoding="utf-8"
            )
            original = hook.REPO_ROOT
            try:
                _patch_repo_paths(hook, tmp)
                rc, err = self._run(tmp)
            finally:
                _patch_repo_paths(hook, original)
            self.assertEqual(rc, 0, err)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
