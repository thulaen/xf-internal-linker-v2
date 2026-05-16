"""Tests for the stubs-not-regenerated hook (Rule L, 2026-05-16).

Five cases:
  1. No staged files -> pass
  2. Stubs changed AND contract changed -> pass (legitimate regen)
  3. Stubs changed but contract NOT -> FAIL naming the service
  4. Contract changed but stubs NOT -> pass (the regen will happen later)
  5. Two services - one clean (both changed), one dirty (stub-only) -> FAIL
     listing only the dirty one
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    module_name = "check_stubs_not_regenerated"
    path = HOOKS_DIR / "check-stubs-not-regenerated.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class _FakeCompleted:
    def __init__(self, stdout: str = ""):
        self.stdout = stdout
        self.returncode = 0
        self.stderr = ""


def _patch_diff(paths: list[str]):
    def fake_run(cmd, **_kwargs):
        if "--name-only" in " ".join(cmd):
            return _FakeCompleted(stdout="\n".join(paths) + "\n")
        return _FakeCompleted()
    # The hook delegates to _hook_helpers.staged_paths which calls
    # subprocess.run in the helpers module.
    from _hook_helpers import subprocess as helpers_subprocess
    return patch.object(helpers_subprocess, "run", side_effect=fake_run)


class StubsNotRegeneratedTests(TestCase):

    def _run(self, paths: list[str]) -> tuple[int, str]:
        captured = io.StringIO()
        with _patch_diff(paths), patch.object(hook.sys, "stderr", captured):
            return hook.main(), captured.getvalue()

    def test_empty_diff_passes(self) -> None:
        rc, _ = self._run([])
        self.assertEqual(rc, 0)

    def test_stubs_with_matching_contract_passes(self) -> None:
        rc, _ = self._run([
            "services/streamd/api.proto",
            "services/streamd/api/gen/api.pb.go",
            "services/streamd/api/gen/api_grpc.pb.go",
            "backend/apps/realtime/_streamd_pb2/api_pb2.py",
        ])
        self.assertEqual(rc, 0)

    def test_stubs_without_contract_fails(self) -> None:
        rc, err = self._run([
            "services/streamd/api/gen/api.pb.go",
            "services/streamd/api/gen/api_grpc.pb.go",
        ])
        self.assertEqual(rc, 2)
        self.assertIn("FAIL check-stubs-not-regenerated", err)
        self.assertIn("WHY:", err)
        self.assertIn("UNBLOCK:", err)
        self.assertIn("streamd", err)

    def test_contract_without_stubs_passes(self) -> None:
        """The hook only fires when stubs change WITHOUT a contract. The
        reverse (contract change without stubs yet) is the normal first
        step of a regen flow and is allowed."""
        rc, _ = self._run(["services/streamd/api.proto"])
        self.assertEqual(rc, 0)

    def test_multi_service_only_flags_the_dirty_one(self) -> None:
        rc, err = self._run([
            "services/streamd/api.proto",
            "services/streamd/api/gen/api.pb.go",
            "services/webhookd/api/gen/api.pb.go",  # stub-only - dirty
        ])
        self.assertEqual(rc, 2)
        self.assertIn("webhookd", err)
        self.assertNotIn("streamd - stubs changed", err)

    def test_python_pb2_stubs_are_also_watched(self) -> None:
        rc, err = self._run([
            "backend/apps/realtime/_streamd_pb2/api_pb2_grpc.py",
        ])
        self.assertEqual(rc, 2)
        self.assertIn("streamd", err)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
