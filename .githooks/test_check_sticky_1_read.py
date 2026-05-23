#!/usr/bin/env python3
"""Tests for ``.githooks/check-sticky-1-read.py``.

Stubs both `_staged_code_files` / `_staged_handoff_diff` (via patch on
hook internals) and `_live_sticky_sha` so no live Docker or git call
is needed. Covers the 7 documented scenarios from
docs/specs/fr-sticky-1-read-rule.md.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-sticky-1-read.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_sticky_1_read_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-sticky-1-read.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class _StderrCollector:
    def __init__(self, bucket: list[str]) -> None:
        self._bucket = bucket

    def write(self, msg: str) -> int:
        self._bucket.append(msg)
        return len(msg)

    def flush(self) -> None:  # pragma: no cover
        return None


def _run_with(
    *,
    code_files: list[str],
    handoff: str,
    live_sha: str | None = "7b8d04510bf49e49",
) -> tuple[int, str]:
    captured: list[str] = []
    with patch.object(
        hook, "_staged_code_files", return_value=code_files
    ), patch.object(
        hook, "_staged_handoff_diff", return_value=handoff
    ), patch.object(
        hook, "_live_sticky_sha", return_value=live_sha
    ), patch.object(hook.sys, "stderr", new=_StderrCollector(captured)):
        rc = hook.main()
    return rc, "".join(captured)


class HappyPathTests(unittest.TestCase):
    def test_marker_present_and_sha_matches_returns_zero(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff=(
                "[REGISTRY READ: 5 open]\n"
                "[STICKY 1 READ: timestamp=2026-05-23T03:54:22Z "
                "sha256=7b8d04510bf49e49 agent=claude]\n"
                "[GUIDELINES READ: ...]\n"
            ),
        )
        self.assertEqual(rc, 0, msg=out)


class ExemptionTests(unittest.TestCase):
    def test_bootstrap_marker_short_circuits(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/paper_trail/models.py"],
            handoff="[STICKY 1 BOOTSTRAP: commit=introduces-sticky]\n",
        )
        self.assertEqual(rc, 0, msg=out)

    def test_edit_marker_short_circuits(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/paper_trail/models.py"],
            handoff=(
                "[STICKY 1 EDIT: previous_sha=abcdef1234567890 "
                'new_sha=fedcba0987654321 reason="add new rule"]\n'
            ),
        )
        self.assertEqual(rc, 0, msg=out)

    def test_pure_docs_commit_exempt(self) -> None:
        rc, out = _run_with(
            code_files=[],  # no code-staging-surface files
            handoff="",
        )
        self.assertEqual(rc, 0, msg=out)


class FailureTests(unittest.TestCase):
    def test_missing_marker_on_code_commit_blocks(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REGISTRY READ: 5 open]\n[GUIDELINES READ: ...]\n",
        )
        self.assertEqual(rc, 2)
        self.assertIn("STICKY 1 READ", out)
        self.assertIn("manage.py read_sticky --id 1", out)

    def test_stale_sha_blocks_with_reread_prompt(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff=(
                "[STICKY 1 READ: timestamp=2026-05-23T03:54:22Z "
                "sha256=0000000000000000 agent=claude]\n"
            ),
            live_sha="7b8d04510bf49e49",
        )
        self.assertEqual(rc, 2)
        self.assertIn("0000000000000000", out)
        self.assertIn("7b8d04510bf49e49", out)
        self.assertIn("read_sticky", out)

    def test_live_sha_unreachable_blocks(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff=(
                "[STICKY 1 READ: timestamp=2026-05-23T03:54:22Z "
                "sha256=7b8d04510bf49e49 agent=claude]\n"
            ),
            live_sha=None,
        )
        self.assertEqual(rc, 2)
        self.assertIn("live SHA", out)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
