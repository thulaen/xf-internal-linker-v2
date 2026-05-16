#!/usr/bin/env python3
"""Tests for check-spec-citation.py (Rule C hard-block)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_spec_citation", here / "check-spec-citation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpecCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_new_specs_passes(self):
        with mock.patch.object(self.hook, "_staged_new_specs", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_spec_without_citation_fails(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text("# Example\n\nNo citation here.", encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs",
                                   return_value=["docs/specs/example.md"]), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                self.assertEqual(self.hook.main(), 2)
                msg = err.getvalue()
                self.assertIn("FAIL", msg)
                self.assertIn("WHY", msg)
                self.assertIn("UNBLOCK", msg)

    def test_spec_with_citation_passes(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "docs/specs/example.md"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                "# Example\n\n[SPEC CITED: feature=example kind=doi "
                "id=10.1/example verified_at=2026-05-15T00:00:00Z]",
                encoding="utf-8",
            )
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_new_specs",
                                   return_value=["docs/specs/example.md"]):
                self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
