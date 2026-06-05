#!/usr/bin/env python3
"""Unit tests for the diff-scoped mutmut helper `_mutmut_diff_scope.py`.

Two things are locked here:

1. The Phase-B regression. mutmut 2.x `mutmut run` accepts EXACTLY ONE
   positional (a single mutant id OR a file path). The old Phase B passed the
   whole keep list in one call (`mutmut run 1 2 3`), which mutmut rejects with
   exit 2 WITHOUT testing anything — so every kept mutant kept its Phase-A
   no-op 'survived' verdict and surfaced as a FALSE survivor whenever >=2
   changed-line mutants existed. Every Phase-B call must carry one positional.

2. Per-file test scoping. Each source file's mutants must be re-tested against
   ONLY that file's own tests, not the flat union (the difference between a
   feasible gate and a timeout when several files are staged).

No Docker / no mutmut needed: subprocess.run is mocked.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

_MOD_PATH = Path(__file__).with_name("_mutmut_diff_scope.py")


def _load():
    spec = importlib.util.spec_from_file_location("_mutmut_diff_scope", _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PhaseBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_runs_one_mutmut_call_per_plan_entry(self):
        plan = [("1", "RUN_A"), ("2", "RUN_B"), ("apps/x.py", "RUN_C")]
        with mock.patch.object(self.mod.subprocess, "run") as run:
            self.mod._phase_b(plan)
        self.assertEqual(run.call_count, 3)
        positionals = [call.args[0][2] for call in run.call_args_list]
        self.assertEqual(positionals, ["1", "2", "apps/x.py"])

    def test_each_call_carries_exactly_one_positional_and_its_runner(self):
        plan = [("7", "RUN_7"), ("8", "RUN_8")]
        with mock.patch.object(self.mod.subprocess, "run") as run:
            self.mod._phase_b(plan)
        for call, (pos, runner) in zip(run.call_args_list, plan):
            argv = call.args[0]
            self.assertEqual(argv[:2], ["mutmut", "run"])
            self.assertEqual(argv.index("--runner"), 3)  # exactly one positional
            self.assertEqual(argv[2], pos)
            self.assertEqual(argv[4], runner)

    def test_empty_plan_runs_nothing(self):
        with mock.patch.object(self.mod.subprocess, "run") as run:
            self.mod._phase_b([])
        run.assert_not_called()


class PhaseBPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_fully_kept_file_collapses_to_one_file_path(self):
        located = {"1": ("apps/a.py", 3), "2": ("apps/a.py", 4)}
        by_file_all = {"apps/a.py": ["1", "2"]}
        tests_map = {"apps/a.py": ["apps/tests/test_a.py"]}
        plan = self.mod._phase_b_plan(["1", "2"], located, by_file_all, tests_map)
        self.assertEqual([p for p, _ in plan], ["apps/a.py"])
        self.assertIn("apps/tests/test_a.py", plan[0][1])

    def test_partially_kept_file_uses_individual_ids(self):
        located = {"1": ("apps/b.py", 3), "2": ("apps/b.py", 4)}
        by_file_all = {"apps/b.py": ["1", "2", "3"]}  # 3 mutants, only 2 kept
        tests_map = {"apps/b.py": ["apps/tests/test_b.py"]}
        plan = self.mod._phase_b_plan(["1", "2"], located, by_file_all, tests_map)
        self.assertEqual([p for p, _ in plan], ["1", "2"])

    def test_runner_is_scoped_per_file(self):
        located = {"1": ("apps/a.py", 1), "2": ("apps/b.py", 9)}
        by_file_all = {"apps/a.py": ["1"], "apps/b.py": ["2", "3"]}
        tests_map = {"apps/a.py": ["t_a.py"], "apps/b.py": ["t_b.py"]}
        plan = dict(self.mod._phase_b_plan(["1", "2"], located, by_file_all, tests_map))
        self.assertIn("t_a.py", plan["apps/a.py"])
        self.assertNotIn("t_b.py", plan["apps/a.py"])
        self.assertIn("t_b.py", plan["2"])  # the lone kept id in b
        self.assertNotIn("t_a.py", plan["2"])

    def test_no_batched_positional_ever_emitted(self):
        located = {"1": ("apps/b.py", 3)}
        by_file_all = {"apps/b.py": ["1", "2"]}
        tests_map = {"apps/b.py": ["t_b.py"]}
        for pos, _ in self.mod._phase_b_plan(["1"], located, by_file_all, tests_map):
            self.assertNotIn(" ", pos)
            self.assertNotIn(",", pos)


class TestsMapAndRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_parse_tests_map_reads_tokens(self):
        m = self.mod._parse_tests_map(
            ["apps/a.py::t1.py,t2.py", "apps/b.py::t3.py"], "", "apps/a.py,apps/b.py"
        )
        self.assertEqual(m["apps/a.py"], ["t1.py", "t2.py"])
        self.assertEqual(m["apps/b.py"], ["t3.py"])

    def test_missing_path_falls_back_to_union(self):
        m = self.mod._parse_tests_map([], "u1.py u2.py", "apps/c.py")
        self.assertEqual(m["apps/c.py"], ["u1.py", "u2.py"])

    def test_empty_scoped_list_falls_back_to_union(self):
        # A file with no convention test (token `rel::`) must NOT map to [] —
        # it falls through to the union so `_runner_for([])` can never happen.
        m = self.mod._parse_tests_map(
            ["apps/a.py::"], "u1.py u2.py", "apps/a.py"
        )
        self.assertEqual(m["apps/a.py"], ["u1.py", "u2.py"])

    def test_runner_for_includes_reuse_db_and_tests(self):
        r = self.mod._runner_for(["apps/tests/test_x.py"])
        self.assertIn("--reuse-db", r)
        self.assertIn("apps/tests/test_x.py", r)
        self.assertIn("python -m pytest", r)


class ParseChangedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_all_token_maps_to_all_sentinel(self):
        changed = self.mod._parse_changed(["apps/x.py:ALL"])
        self.assertEqual(changed["apps/x.py"], "ALL")

    def test_line_token_maps_to_int_set(self):
        changed = self.mod._parse_changed(["apps/x.py:12,15,15"])
        self.assertEqual(changed["apps/x.py"], {12, 15})

    def test_on_changed_respects_all_and_membership(self):
        changed = {"apps/a.py": "ALL", "apps/b.py": {5}}
        self.assertTrue(self.mod._on_changed(("apps/a.py", 99), changed))
        self.assertTrue(self.mod._on_changed(("apps/b.py", 5), changed))
        self.assertFalse(self.mod._on_changed(("apps/b.py", 6), changed))
        self.assertFalse(self.mod._on_changed(("apps/c.py", 1), changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
