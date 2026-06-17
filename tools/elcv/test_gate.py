#!/usr/bin/env python3
"""Tests for the ELCV hard-block gate. Run:  python tools/elcv/test_gate.py"""
from __future__ import annotations

import ast
import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate  # noqa: E402


def rules(source: str, path: str = "prod.py") -> set[str]:
    """Return the set of rule-id prefixes raised for *source*."""
    return {f.rule.split("-", 1)[0] for f in gate.gate_source(textwrap.dedent(source), path)}


class GateTests(unittest.TestCase):
    def test_long_function(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(60))
        self.assertIn("ELCV001", rules(f"def f():\n{body}\n"))

    def test_oversized_file(self):
        src = "x = 1\n" * 1300
        self.assertIn("ELCV002", rules(src))

    def test_high_complexity(self):
        body = "\n".join(f"    if a == {i}: a += 1" for i in range(12))
        self.assertIn("ELCV003", rules(f"def f(a):\n{body}\n"))

    def test_deep_nesting(self):
        src = """
            def f(a):
                if a:
                    for i in a:
                        while i:
                            with open('x') as h:
                                if h:
                                    return 1
        """
        self.assertIn("ELCV005", rules(src))

    def test_too_many_params(self):
        self.assertIn("ELCV006", rules("def f(a, b, c, d, e, g, h, i):\n    return 1\n"))

    def test_boolean_trap(self):
        self.assertIn("ELCV007", rules("def f(a=True, b=False, c=True):\n    return a\n"))

    def test_too_many_returns(self):
        body = "\n".join(f"    if a == {i}: return {i}" for i in range(6))
        self.assertIn("ELCV008", rules(f"def f(a):\n{body}\n    return -1\n"))

    def test_god_class(self):
        methods = "\n".join(f"    def m{i}(self): return {i}" for i in range(21))
        self.assertIn("ELCV011", rules(f"class C:\n{methods}\n"))

    def test_wildcard_import(self):
        self.assertIn("ELCV012", rules("from os import *\n"))

    def test_mutable_default(self):
        self.assertIn("ELCV013", rules("def f(x=[]):\n    return x\n"))

    def test_silent_except(self):
        self.assertIn("ELCV014", rules("try:\n    x = 1\nexcept Exception:\n    pass\n"))

    def test_dead_code(self):
        self.assertIn("ELCV015", rules("def f():\n    return 1\n    x = 2\n"))

    def test_unbounded_loop(self):
        self.assertIn("ELCV016", rules("def f():\n    while True:\n        pass\n"))

    def test_dangerous_exec(self):
        self.assertIn("ELCV017", rules("def f(s):\n    return eval(s)\n"))

    def test_placeholder_stub(self):
        self.assertIn("ELCV018", rules("def f():\n    raise NotImplementedError\n"))

    def test_nested_ternary(self):
        self.assertIn("ELCV019", rules("def f(a, b):\n    return 1 if a else (2 if b else 3)\n"))

    def test_train_wreck(self):
        self.assertIn("ELCV020", rules("def f(o):\n    return o.a.b.c.d.e\n"))

    def test_mutable_global(self):
        self.assertIn("ELCV021", rules("X = 1\ndef f():\n    global X\n    X = 2\n"))

    def test_n_plus_one(self):
        self.assertIn("ELCV026", rules("def f(ids):\n    for i in ids:\n        Model.objects.get(id=i)\n"))

    def test_dict_get_inside_loop_is_not_n_plus_one(self):
        source = "def f(items, names):\n    for item in items:\n        names.get(item, 'missing')\n"
        self.assertNotIn("ELCV026", rules(source))

    def test_orphan_todo(self):
        self.assertIn("ELCV023", rules("# TODO: fix this later\nx = 1\n"))

    def test_referenced_todo_allowed(self):
        self.assertNotIn("ELCV023", rules("# TODO (AutoIssue #42): fix this later\nx = 1\n"))

    def test_blanket_suppression(self):
        self.assertIn("ELCV024", rules("import os  # noqa\n"))

    def test_hardcoded_secret(self):
        self.assertIn("ELCV027", rules('api_key = "abcdef123456"\n'))

    def test_cross_module_private_import(self):
        self.assertIn("ELCV029", rules("from apps.pipeline.services import ranker\n"))

    def test_same_app_private_import_allowed(self):
        source = "from apps.audit.services import test_database_shards\n"
        found = rules(source, path="backend/apps/audit/management/commands/x.py")
        self.assertNotIn("ELCV029", found)

    def test_inline_suppression_escape(self):
        src = "def f(x=[]):  # elcv: allow ELCV013 -- legacy, tracked\n    return x\n"
        self.assertNotIn("ELCV013", rules(src))

    def test_cross_file_duplicate(self):
        idx = {h: f"a.py::{n}::{ln}"
               for h, ln, n in gate._function_units(ast.parse("def calc(p):\n    return p + 1\n"))}
        found = {f.rule.split("-", 1)[0]
                 for f in gate.gate_source("def helper(q):\n    return q + 1\n", "b.py", uso_index=idx)}
        self.assertIn("ELCV031", found)

    def test_same_file_not_cross_file_dup(self):
        src = "def calc(p):\n    return p + 1\n"
        idx = {h: f"a.py::{n}::{ln}" for h, ln, n in gate._function_units(ast.parse(src))}
        found = {f.rule for f in gate.gate_source(src, "a.py", uso_index=idx)}
        self.assertNotIn("ELCV031-cross-file-duplicate", found)

    def test_framework_add_arguments_not_cross_file_dup(self):
        src = (
            "def add_arguments(self, parser):\n"
            "    parser.add_argument('--limit', type=int, default=10)\n"
        )
        idx = {h: f"a.py::{n}::{ln}" for h, ln, n in gate._function_units(ast.parse(src))}
        found = {f.rule for f in gate.gate_source(src, "b.py", uso_index=idx)}
        self.assertNotIn("ELCV031-cross-file-duplicate", found)

    def test_baseline_grandfathers_existing(self):
        bad = "def bad(a, b, c, d, e, f, g, h):\n    return 1\n"
        findings = gate.gate_source(bad, "x.py")
        self.assertTrue(findings)
        self.assertEqual(gate.filter_baseline(findings, {f.key for f in findings}), [])

    def test_baseline_ignores_measured_count_churn(self):
        old_key = "ELCV002-oversized-file|x.py|file is 1201 lines (max 1200); refactor/split"
        new = gate.Finding(
            "ELCV002-oversized-file",
            "x.py",
            1202,
            "file is 1202 lines (max 1200); refactor/split",
        )
        self.assertEqual(gate.filter_baseline([new], {old_key}), [])

    def test_clean_code_passes(self):
        src = """
            from apps.graph.api import get_current_run


            def tidy(value: int) -> int:
                if value > 0:
                    return value
                return 0
        """
        self.assertEqual(rules(src), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
