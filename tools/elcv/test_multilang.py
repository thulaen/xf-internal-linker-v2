#!/usr/bin/env python3
"""Tests for the Rust/TS heuristic counters. Run: python tools/elcv/test_multilang.py"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import multilang  # noqa: E402


class RustTests(unittest.TestCase):
    def test_counts_decisions_and_units(self):
        src = (
            "fn a(x: i32) -> i32 { if x > 0 { x } else { -x } }\n"
            "fn b() { for i in 0..3 { match i { 0 => {}, _ => {} } } }\n"
        )
        leu, units = multilang.count_source(src, ".rs")
        self.assertEqual(units, 2)            # two fn
        self.assertEqual(leu, 5)              # if + for + match + two => arms

    def test_ignores_keywords_in_comments_and_strings(self):
        src = 'fn a() { let s = "if for while match"; /* if for */ let _ = s; }\n'
        leu, units = multilang.count_source(src, ".rs")
        self.assertEqual(leu, 0)
        self.assertEqual(units, 1)


class TsTests(unittest.TestCase):
    def test_counts_decisions_and_units(self):
        src = (
            "function a(x: number) { if (x) { return 1; } for (;;) { break; } }\n"
            "const b = () => (x ? 1 : 2);\n"
        )
        leu, units = multilang.count_source(src, ".ts")
        self.assertEqual(leu, 3)              # if + for + ternary ?
        self.assertEqual(units, 2)            # function + arrow =>

    def test_optional_chaining_not_counted_as_ternary(self):
        src = "const f = (o) => o?.a ?? 1;\n"   # ?. and ?? must NOT count as a decision
        leu, _ = multilang.count_source(src, ".ts")
        self.assertEqual(leu, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
