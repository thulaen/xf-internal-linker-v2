#!/usr/bin/env python3
"""Tests for the ELCV computor. Run:  python tools/elcv/test_elcv.py -v"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elcv  # noqa: E402


def _write(tmp: str, name: str, source: str) -> Path:
    path = Path(tmp) / name
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _report(source: str) -> elcv.Report:
    with tempfile.TemporaryDirectory() as tmp:
        return elcv.compute_files([_write(tmp, "m.py", source)])


class LeuTests(unittest.TestCase):
    def test_counts_decision_points(self):
        source = """
            def f(x):
                if x:
                    for i in x:
                        pass
                return x and 1
        """
        units = elcv.units_of_source(textwrap.dedent(source))
        # module unit has 0 decisions; the function owns: if + for + (and) = 3
        self.assertEqual(max(u.leu for u in units), 3)

    def test_empty_function_is_zero_leu(self):
        units = elcv.units_of_source("def f():\n    return 1\n")
        self.assertEqual(max(u.leu for u in units), 0)

    def test_match_case_counts(self):
        source = """
            def f(x):
                match x:
                    case 1:
                        pass
                    case _:
                        pass
        """
        units = elcv.units_of_source(textwrap.dedent(source))
        self.assertEqual(max(u.leu for u in units), 2)


class ScwTests(unittest.TestCase):
    def test_simple_code_full_weight(self):
        self.assertEqual(elcv._scw(1), 1.0)
        self.assertEqual(elcv._scw(10), 1.0)

    def test_complex_code_is_penalised_and_flagged(self):
        body = "\n".join(f"    if x{i}: pass" for i in range(19))  # 19 ifs -> cc 20
        units = elcv.units_of_source(f"def f():\n{body}\n")
        worst = max(units, key=lambda u: u.leu)
        self.assertEqual(worst.leu, 19)
        self.assertEqual(worst.scw, 0.5)
        self.assertTrue(worst.over_ceiling)

    def test_scw_never_below_floor(self):
        self.assertGreaterEqual(elcv._scw(1000), 0.5)


class UsoTests(unittest.TestCase):
    def test_renamed_duplicate_collapses(self):
        # a and b are identical logic with different names -> one USO
        report = _report("def a(p):\n    return p + 1\n\ndef b(q):\n    return q + 1\n")
        self.assertEqual(report.uso, 2)  # module unit + one deduped function

    def test_distinct_method_calls_stay_distinct(self):
        report = _report("def a(p):\n    return p.save()\n\ndef b(q):\n    return q.delete()\n")
        self.assertEqual(report.uso, 3)  # module + save() + delete()

    def test_different_called_functions_stay_distinct(self):
        report = _report("def a(p):\n    return len(p)\n\ndef b(q):\n    return sorted(q)\n")
        self.assertEqual(report.uso, 3)  # free names len/sorted are kept


class ScanTests(unittest.TestCase):
    def test_should_skip_classification(self):
        self.assertTrue(elcv.should_skip(Path("a/node_modules/b.py")))
        self.assertTrue(elcv.should_skip(Path("x/test_foo.py")))
        self.assertTrue(elcv.should_skip(Path("app/migrations/0001_initial.py")))
        # Django-style test files (no test_ prefix) must also be excluded
        self.assertTrue(elcv.should_skip(Path("app/tests.py")))
        self.assertTrue(elcv.should_skip(Path("app/tests_dashboard_helpers.py")))
        self.assertTrue(elcv.should_skip(Path("app/foo_tests.py")))
        self.assertTrue(elcv.should_skip(Path("app/tests/test_x.py")))
        self.assertFalse(elcv.should_skip(Path("backend/apps/pipeline/services/ranker.py")))

    def test_syntax_error_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "good.py", "def f():\n    return 1\n")
            _write(tmp, "bad.py", "def (((:\n")
            report = elcv.compute_path(Path(tmp))
        self.assertEqual(report.files, 1)

    def test_deterministic(self):
        source = "def f(x):\n    if x:\n        return x\n    return 0\n"
        self.assertEqual(_report(source).elcv, _report(source).elcv)

    def test_elcv_formula(self):
        # one function, 1 decision (if), scw 1.0 -> leu_weighted 1.0; units: module + f.
        report = _report("def f(x):\n    if x:\n        return 1\n    return 0\n")
        self.assertEqual(report.leu_weighted, 1.0)
        self.assertEqual(report.uso, 2)
        self.assertEqual(report.elcv, 3.0)  # (1 x 1.0) + 2


if __name__ == "__main__":
    unittest.main(verbosity=2)
