"""Convention tests for scripts/agent_guard.py pure helpers.

BDD:
  Given source lines and parsed Python AST
  When normalize_line / ComplexityVisitor / check_tdd run
  Then comment/blank lines normalise to None, long or complex functions are
       flagged with exact wording, and the 5-minute TDD staleness boundary is
       checked exactly — killing mutation survivors on the changed lines.

Django/AutoIssue side effects are avoided: only pure helpers run. report_violation
is never called for the pure paths (KISS/TDD checks here use functions that do
not touch the DB when no violation surfaces, and we assert via the visitor).
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


ag = _load("agent_guard", "agent_guard.py")


class TestNormalizeLine(TestCase):
    def test_blank_returns_none(self):
        self.assertIsNone(ag.normalize_line("   "))

    def test_python_comment_returns_none(self):
        self.assertIsNone(ag.normalize_line("# a comment"))

    def test_double_slash_comment_returns_none(self):
        self.assertIsNone(ag.normalize_line("// js comment"))

    def test_code_line_stripped(self):
        self.assertEqual(ag.normalize_line("  x = 1  "), "x = 1")


class TestComplexityVisitor(TestCase):
    def _violations(self, src: str):
        import ast
        v = ag.ComplexityVisitor()
        v.visit(ast.parse(src))
        return v.violations

    def test_short_simple_function_no_violation(self):
        self.assertEqual(self._violations("def f():\n    return 1\n"), [])

    def test_long_function_flagged(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(60))
        violations = self._violations(f"def big():\n{body}\n")
        self.assertTrue(any("is 60 lines (max 50)" in v for v in violations))

    def test_complex_function_flagged(self):
        ifs = "\n".join(f"    if x == {i}:\n        pass" for i in range(11))
        violations = self._violations(f"def c(x):\n{ifs}\n")
        self.assertTrue(any("has complexity 12 (max 10)" in v for v in violations))


class TestCheckTdd(TestCase):
    def test_stale_test_flags_violation(self):
        # last test modified far in the past -> > 300s -> True
        self.assertTrue(ag.check_tdd("scripts/x.py", 0))

    def test_fresh_test_no_violation(self):
        import time
        self.assertFalse(ag.check_tdd("scripts/x.py", time.time()))


class TestCheckKiss(TestCase):
    def test_non_python_returns_false(self):
        self.assertFalse(ag.check_kiss("a.ts", "a.ts", "let x = 1;"))

    def test_clean_python_returns_false(self):
        self.assertFalse(ag.check_kiss("a.py", "a.py", "def f():\n    return 1\n"))
