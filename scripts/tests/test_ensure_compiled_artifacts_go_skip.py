"""Convention test for ensure_compiled_artifacts._record_go_state Go-skip.

BDD:
  Given Go source modules whose artifacts are stale
  When _record_go_state runs and the `go` toolchain is absent (shutil.which None)
  Then the rebuild is skipped: _build_go_modules and _write_manifest are NOT
       called, so a Go-source change can never crash the backend boot.
  And when `go` IS present the rebuild path proceeds (build + write happen) —
       killing the mutation that flips the `shutil.which("go") is None` guard.

All Go discovery, hashing, building, and filesystem writes are monkeypatched —
no real toolchain, no filesystem mutation, no subprocess.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


eca = _load("ensure_compiled_artifacts", "ensure_compiled_artifacts.py")


class _Recorder:
    def __init__(self):
        self.built = False
        self.written = False


class TestRecordGoStateSkip(TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = {
            "_go_module_roots": eca._go_module_roots,
            "_go_files_in_modules": eca._go_files_in_modules,
            "_hash_files": eca._hash_files,
            "_build_go_modules": eca._build_go_modules,
            "_write_manifest": eca._write_manifest,
            "_go_manifest_entry": eca._go_manifest_entry,
            "shutil": eca.shutil,
        }
        eca._go_module_roots = lambda repo_root: [Path("services/streamd")]
        eca._go_files_in_modules = lambda modules: ["main.go"]
        eca._hash_files = lambda files: "stalehash"

        def _fake_build(modules, manifest):
            self.rec.built = True
            return []

        def _fake_write(manifest):
            self.rec.written = True

        eca._build_go_modules = _fake_build
        eca._write_manifest = _fake_write
        eca._go_manifest_entry = lambda source_hash, records: {}

    def tearDown(self):
        for name, value in self._orig.items():
            setattr(eca, name, value)

    def _manifest(self):
        return {"active": {"go_runtime": {"source_hash": "old"}}}

    def test_skips_build_when_go_absent(self):
        class _NoGo:
            @staticmethod
            def which(name):
                return None

        eca.shutil = _NoGo()
        eca._record_go_state(Path("/repo"), self._manifest())
        self.assertFalse(self.rec.built, "Go build must be skipped when go is absent")
        self.assertFalse(self.rec.written, "Manifest must not be written on skip")

    def test_builds_when_go_present(self):
        class _HasGo:
            @staticmethod
            def which(name):
                return "/usr/bin/go"

        eca.shutil = _HasGo()
        eca._record_go_state(Path("/repo"), self._manifest())
        self.assertTrue(self.rec.built, "Go build must run when go is present")
        self.assertTrue(self.rec.written, "Manifest must be written when build runs")
