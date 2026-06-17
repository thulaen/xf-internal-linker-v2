#!/usr/bin/env python3
"""Tests for the tree-sitter true-AST Rust/TS counter.

These run only where tree-sitter + the grammars are installed (CI / quality container);
they SKIP cleanly on a host without the optional dependency. Run:
    pip install -r tools/elcv/requirements.txt
    python tools/elcv/test_ts_backend.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ts_backend  # noqa: E402


def _count(name: str, source: str):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, name).write_text(source, encoding="utf-8")
        return ts_backend.count_paths(Path(tmp))


@unittest.skipUnless(ts_backend.available(), "tree-sitter / grammars not installed")
class RustAstTests(unittest.TestCase):
    def test_decisions_and_dedup(self):
        src = ("fn a(x: i32) -> i32 { if x > 0 { x } else { -x } }\n"
               "fn b(y: i32) -> i32 { if y > 0 { y } else { -y } }\n")
        r = _count("m.rs", src)["rust"]
        self.assertEqual(r.files, 1)
        self.assertEqual(r.uso, 1)                 # two renamed-identical fns collapse
        self.assertGreaterEqual(r.leu_weighted, 2)  # one `if` each

    def test_distinct_methods_not_collapsed(self):
        src = "fn a(x: T) { x.save(); }\nfn b(y: T) { y.delete(); }\n"
        r = _count("m.rs", src)["rust"]
        self.assertEqual(r.uso, 2)                 # save() vs delete() stay distinct


@unittest.skipUnless(ts_backend.available(), "tree-sitter / grammars not installed")
class TsAstTests(unittest.TestCase):
    def test_decisions_and_dedup(self):
        src = ("function a(x: number) { return x ? 1 : 2; }\n"
               "function b(y: number) { return y ? 1 : 2; }\n")
        r = _count("m.ts", src)["typescript"]
        self.assertEqual(r.uso, 1)                 # identical ternary fns collapse
        self.assertGreaterEqual(r.leu_weighted, 2)  # one ternary each


if __name__ == "__main__":
    unittest.main(verbosity=2)
