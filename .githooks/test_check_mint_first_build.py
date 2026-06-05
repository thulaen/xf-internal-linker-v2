#!/usr/bin/env python3
"""Tests for ``.githooks/check-mint-first-build.py``.

The guard enforces the mint-first build-routing rule (config/docker-build-
routing.json: mint 65 / windows 35): committed scripts must not invoke a raw
``docker build`` / ``docker compose build`` / ``docker buildx build``. They
must route through the smart build helper (``scripts/build-smart.ps1`` /
``scripts/smart_build.py``) so compilation honours the 65/35 split instead of
always building locally on Windows.

These tests exercise the pure ``scan_text`` core so no real git/staging is
needed.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent / "check-mint-first-build.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_mint_first_build_uut", _HOOK_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-mint-first-build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load()


class ScanTextTests(unittest.TestCase):
    def test_raw_docker_compose_build_is_flagged(self) -> None:
        v = hook.scan_text("scripts/foo.sh", "docker compose build backend\n")
        self.assertTrue(v, "raw `docker compose build` must be flagged")

    def test_raw_docker_build_is_flagged(self) -> None:
        v = hook.scan_text("scripts/foo.sh", "docker build -t x .\n")
        self.assertTrue(v)

    def test_raw_buildx_build_is_flagged(self) -> None:
        v = hook.scan_text("scripts/foo.ps1", "docker buildx build --tag x .\n")
        self.assertTrue(v)

    def test_build_smart_invocation_is_allowed(self) -> None:
        v = hook.scan_text("scripts/foo.ps1", "& scripts/build-smart.ps1 --target backend\n")
        self.assertFalse(v, "routing through build-smart must pass")

    def test_smart_build_invocation_is_allowed(self) -> None:
        v = hook.scan_text("scripts/foo.sh", "python scripts/smart_build.py --target backend\n")
        self.assertFalse(v)

    def test_comment_is_allowed(self) -> None:
        v = hook.scan_text("scripts/foo.sh", "# docker compose build backend  (example only)\n")
        self.assertFalse(v, "commented build commands must not be flagged")

    def test_router_files_are_exempt(self) -> None:
        # The router itself MUST call the real docker build.
        self.assertFalse(hook.scan_text("scripts/smart_build.py", "docker compose build backend\n"))
        self.assertFalse(hook.scan_text("scripts/build-smart.ps1", "docker compose build backend\n"))

    def test_docker_compose_run_is_not_a_build(self) -> None:
        v = hook.scan_text("scripts/foo.sh", "docker compose run --rm backend-quality sh -lc 'x'\n")
        self.assertFalse(v, "`run` is not a build and must not be flagged")

    def test_is_scanned_path_filters_extensions(self) -> None:
        self.assertTrue(hook.is_scanned_path("scripts/x.sh"))
        self.assertTrue(hook.is_scanned_path("scripts/x.ps1"))
        self.assertTrue(hook.is_scanned_path("a/b.py"))
        self.assertFalse(hook.is_scanned_path("docs/x.md"))
        self.assertFalse(hook.is_scanned_path(".githooks/test_check_mint_first_build.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
