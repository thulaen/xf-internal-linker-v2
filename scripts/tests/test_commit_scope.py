"""Convention tests for scripts/commit_scope.normalize_paths generated filter.

BDD:
  Given raw git status path lines
  When normalize_paths cleans them
  Then backslashes become slashes, blank lines drop, the result is sorted, and
       generated paths (by exact name, prefix, or suffix) are filtered out —
       killing mutation survivors on the new GENERATED_SCOPE_* filtering lines.

Pure string logic only — no git subprocess invoked.
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


cs = _load("commit_scope", "commit_scope.py")


class TestNormalizePaths(TestCase):
    def test_backslashes_to_slashes_and_sorted(self):
        out = cs.normalize_paths("b\\y.py\na/x.py\n")
        self.assertEqual(out, ["a/x.py", "b/y.py"])

    def test_blank_lines_dropped(self):
        out = cs.normalize_paths("a.py\n\n   \nb.py\n")
        self.assertEqual(out, ["a.py", "b.py"])

    def test_generated_prefix_filtered(self):
        out = cs.normalize_paths(".tmp/blob.json\nkeep.py\n")
        self.assertEqual(out, ["keep.py"])

    def test_generated_exact_filtered(self):
        out = cs.normalize_paths("luacov.stats.out\nkeep.py\n")
        self.assertEqual(out, ["keep.py"])

    def test_generated_suffix_filtered(self):
        out = cs.normalize_paths("something.tmp\nkeep.py\n")
        self.assertEqual(out, ["keep.py"])

    def test_mutmut_cache_prefix_filtered(self):
        out = cs.normalize_paths("backend/.mutmut-cache/x\nkeep.py\n")
        self.assertEqual(out, ["keep.py"])

    def test_real_path_retained(self):
        out = cs.normalize_paths("scripts/commit_scope.py\n")
        self.assertEqual(out, ["scripts/commit_scope.py"])
