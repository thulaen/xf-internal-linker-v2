#!/usr/bin/env python3
"""Tests for ``.githooks/check-dead-code-on-replace.py``.

The guard enforces the dead-code-on-replace rule from
``docs/PYTHON-RUST-MIGRATION-PLAN.md`` § "Dead-code handling": when a commit
deletes a module (a Python fallback after a Rust port, a removed-language
source, an orphan), no staged file may still import the deleted module. A
remaining reference is a dangling import that breaks at runtime.

These tests exercise the pure ``dangling_references`` core so no real git or
staging is needed.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent / "check-dead-code-on-replace.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_dead_code_on_replace_uut", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-dead-code-on-replace.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load()

_DELETED = ["backend.apps.pipeline.services.ranker_fallback"]


class DanglingReferencesTests(unittest.TestCase):
    def test_remaining_from_import_is_flagged(self) -> None:
        files = {
            "backend/apps/suggestions/views.py": (
                "from backend.apps.pipeline.services.ranker_fallback import rank\n"
            )
        }
        flagged = hook.dangling_references(_DELETED, files)
        self.assertIn("backend/apps/suggestions/views.py", flagged)

    def test_remaining_import_statement_is_flagged(self) -> None:
        files = {
            "backend/apps/suggestions/api.py": (
                "import backend.apps.pipeline.services.ranker_fallback as rf\n"
            )
        }
        flagged = hook.dangling_references(_DELETED, files)
        self.assertIn("backend/apps/suggestions/api.py", flagged)

    def test_unrelated_import_is_not_flagged(self) -> None:
        files = {
            "backend/apps/suggestions/views.py": (
                "from backend.apps.pipeline.services.ranker import rank\n"
                "import os\n"
            )
        }
        flagged = hook.dangling_references(_DELETED, files)
        self.assertEqual(flagged, [])

    def test_empty_deleted_set_returns_empty(self) -> None:
        files = {
            "backend/apps/suggestions/views.py": (
                "from backend.apps.pipeline.services.ranker_fallback import rank\n"
            )
        }
        flagged = hook.dangling_references([], files)
        self.assertEqual(flagged, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
