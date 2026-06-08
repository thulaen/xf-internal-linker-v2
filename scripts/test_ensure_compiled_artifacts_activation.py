#!/usr/bin/env python3
"""Regression tests for the activation paths in ensure_compiled_artifacts.

The Phase K.5 refactor adds a per-file atomic-replacement fallback
(`_activate_via_file_replacement`) that runs when the rollback-move
activation path (`_activate_via_rollback_move`) hits a
``PermissionError``.  The fallback only needs write access to the
individual ``.so`` files inside ``ACTIVE_EXTENSIONS_ROOT`` and write
access to the parent directory, never permission to unlink the
directory itself.  This means the build completes without requiring a
privileged ``chown`` when an earlier root-mode build left root-owned
files behind.

These tests stub the on-disk paths through ``tmp_path`` so the suite
does not touch the real ``/opt/xf/compiled`` tree.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SCRIPT_PATH = Path(__file__).resolve().parent / "ensure_compiled_artifacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "ensure_compiled_artifacts_under_test", _SCRIPT_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load ensure_compiled_artifacts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eca = _load_module()


class ActivationFallbackTests(unittest.TestCase):
    """The per-file fallback updates active contents without dir unlinks."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="eca-activation-"))
        self.addCleanup(shutil.rmtree, str(self.tmpdir), ignore_errors=True)
        self.active = self.tmpdir / "active" / "extensions"
        self.active.mkdir(parents=True)
        self.stage = self.tmpdir / ".stage-build"
        (self.stage / "extensions").mkdir(parents=True)
        # Pre-populate the active dir with one "old" file the build is
        # about to replace.
        (self.active / "papertrail_dedup.cpython-312.so").write_bytes(b"OLD")
        # Stage a fresh build of the same file plus a new one.
        (self.stage / "extensions" / "papertrail_dedup.cpython-312.so").write_bytes(b"NEW")
        (self.stage / "extensions" / "sticky_lookup.cpython-312.so").write_bytes(b"NEW")

    def test_per_file_replacement_swaps_files_in_place(self) -> None:
        with patch.object(eca, "ACTIVE_EXTENSIONS_ROOT", self.active), patch.object(
            eca, "_ensure_legacy_extension_link", lambda: None
        ):
            eca._activate_via_file_replacement(self.stage)
        self.assertEqual(
            (self.active / "papertrail_dedup.cpython-312.so").read_bytes(), b"NEW"
        )
        self.assertEqual(
            (self.active / "sticky_lookup.cpython-312.so").read_bytes(), b"NEW"
        )
        self.assertFalse(
            self.stage.exists(), msg="stage directory should be cleaned up on success"
        )

    def test_fallback_cleans_temp_files_on_replace_error(self) -> None:
        # Force os.replace to fail; the fallback should leave the
        # active dir clean (no stranded .activate-* files).
        with patch.object(eca, "ACTIVE_EXTENSIONS_ROOT", self.active), patch.object(
            eca, "_ensure_legacy_extension_link", lambda: None
        ), patch.object(eca.os, "replace", side_effect=OSError("forced")):
            with self.assertRaises(OSError):
                eca._activate_via_file_replacement(self.stage)
        leftovers = list(self.active.glob(".activate-*"))
        self.assertEqual(leftovers, [], msg=f"expected no .activate-* leftovers, got {leftovers}")


class ActivationRouteTests(unittest.TestCase):
    """The router calls the file-replacement fallback on PermissionError."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="eca-route-"))
        self.addCleanup(shutil.rmtree, str(self.tmpdir), ignore_errors=True)
        self.active_root = self.tmpdir / "active"
        self.active_extensions = self.active_root / "extensions"
        self.active_extensions.mkdir(parents=True)
        (self.active_extensions / "old.so").write_bytes(b"OLD")
        self.stage = self.tmpdir / ".stage"
        (self.stage / "extensions").mkdir(parents=True)
        (self.stage / "extensions" / "new.so").write_bytes(b"NEW")

    def test_permission_error_triggers_fallback(self) -> None:
        calls: list[str] = []

        def fake_rollback(stage_dir: Path) -> None:
            calls.append("rollback")
            raise PermissionError("simulated root-owned active dir")

        def fake_replacement(stage_dir: Path) -> None:
            calls.append("replacement")

        with patch.object(eca, "ACTIVE_ROOT", self.active_root), patch.object(
            eca, "ACTIVE_EXTENSIONS_ROOT", self.active_extensions
        ), patch.object(eca, "_verify_runtime_imports", lambda _stage: None), patch.object(
            eca, "_prune_rollback_sets", lambda **_kw: None
        ), patch.object(
            eca, "_activate_via_rollback_move", fake_rollback
        ), patch.object(
            eca, "_activate_via_file_replacement", fake_replacement
        ):
            eca._activate_staged_runtime(self.stage)
        self.assertEqual(calls, ["rollback", "replacement"])

    def test_clean_path_skips_fallback(self) -> None:
        calls: list[str] = []

        def fake_rollback(stage_dir: Path) -> None:
            calls.append("rollback")

        def fake_replacement(stage_dir: Path) -> None:  # pragma: no cover - should not run
            calls.append("replacement")

        with patch.object(eca, "ACTIVE_ROOT", self.active_root), patch.object(
            eca, "ACTIVE_EXTENSIONS_ROOT", self.active_extensions
        ), patch.object(eca, "_verify_runtime_imports", lambda _stage: None), patch.object(
            eca, "_prune_rollback_sets", lambda **_kw: None
        ), patch.object(
            eca, "_activate_via_rollback_move", fake_rollback
        ), patch.object(
            eca, "_activate_via_file_replacement", fake_replacement
        ):
            eca._activate_staged_runtime(self.stage)
        self.assertEqual(calls, ["rollback"], msg="fallback should not fire on the clean path")


class RuntimeImportProbeTests(unittest.TestCase):
    """Runtime smoke imports must include Rust-owned kernels."""

    def test_probe_checks_rust_kernel_imports_and_public_names(self) -> None:
        code = eca._runtime_import_probe_code()
        expected = {
            "anchor_self_information": "bigram_entropy",
            "compressed_bloom": "CompressedBloomFilter",
            "count_min_sketch": "CountMinSketch",
            "counting_bloom": "CountingBloomFilter",
            "l2norm": "normalize_l2_batch",
        }
        for module_name, attr_name in expected.items():
            self.assertIn(f"extensions.{module_name}", code)
            self.assertIn(attr_name, code)


class CarryForwardRustKernelsTests(unittest.TestCase):
    """The C++ stage dir must inherit the already-active Rust kernels.

    A kernel ported from C++ to Rust (e.g. ``anchor_self_information``) is built
    by the Rust path, not the C++ build, so the freshly-built C++ stage dir does
    NOT contain its ``.so``. The runtime import probe — run against the stage dir
    inside ``_build_cpp_runtime`` — always imports every Rust kernel, so without
    carrying the active Rust ``.so`` into the stage dir the C++ rebuild crashes
    on ``ModuleNotFoundError: extensions.anchor_self_information`` and the backend
    crash-loops. Carrying them forward also stops the C++ activation move from
    wiping the Rust kernels out of the active dir.
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="eca-carry-"))
        self.addCleanup(shutil.rmtree, str(self.tmpdir), ignore_errors=True)
        self.active = self.tmpdir / "active" / "extensions"
        self.active.mkdir(parents=True)
        # Active dir holds a Rust kernel (bare .so) the C++ build won't produce.
        (self.active / "anchor_self_information.so").write_bytes(b"RUST")
        (self.active / "l2norm.so").write_bytes(b"RUST-L2")
        self.stage = self.tmpdir / ".stage-build"
        (self.stage / "extensions").mkdir(parents=True)
        (self.stage / "extensions" / "scoring.cpython-312.so").write_bytes(b"CPP")

    def test_active_rust_kernels_are_copied_into_stage(self) -> None:
        with patch.object(eca, "ACTIVE_EXTENSIONS_ROOT", self.active):
            eca._carry_forward_rust_kernels_into_stage(self.stage)
        staged = self.stage / "extensions"
        self.assertEqual((staged / "anchor_self_information.so").read_bytes(), b"RUST")
        self.assertEqual((staged / "l2norm.so").read_bytes(), b"RUST-L2")
        # The C++ artifact already in the stage dir is untouched.
        self.assertEqual((staged / "scoring.cpython-312.so").read_bytes(), b"CPP")

    def test_missing_rust_kernel_is_skipped_without_error(self) -> None:
        # Only one Rust kernel present in active; the rest simply aren't carried.
        (self.active / "l2norm.so").unlink()
        with patch.object(eca, "ACTIVE_EXTENSIONS_ROOT", self.active):
            eca._carry_forward_rust_kernels_into_stage(self.stage)
        staged = self.stage / "extensions"
        self.assertTrue((staged / "anchor_self_information.so").exists())
        self.assertFalse((staged / "l2norm.so").exists())

    def test_no_active_dir_is_a_noop(self) -> None:
        empty_active = self.tmpdir / "nope" / "extensions"
        with patch.object(eca, "ACTIVE_EXTENSIONS_ROOT", empty_active):
            # Must not raise even when the active dir does not exist yet.
            eca._carry_forward_rust_kernels_into_stage(self.stage)
        self.assertTrue((self.stage / "extensions" / "scoring.cpython-312.so").exists())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(unittest.main(verbosity=2))
