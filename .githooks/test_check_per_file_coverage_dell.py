#!/usr/bin/env python3
"""Unit tests for the Dell 80% / Windows 20% coverage split in
check-per-file-coverage.py. All docker/subprocess boundaries are mocked, so
these run on host python with no Docker, no Dell, and no real coverage run —
exactly like test_check_scoped_mutation_dell.py.

Covers: the 80/20 partition, the Dell command builder, the merge, and the
fail-open paths (no Dell -> all local; Dell sync/verify fail -> re-measure that
slice locally; XF_COVERAGE_SPLIT unset -> today's local-only behaviour).
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cov = _load("check_per_file_coverage", ".githooks/check-per-file-coverage.py")
routing = _load("machine_routing", "scripts/machine_routing.py")


def _machines(*names):
    """Build a machine list like _select_machines would return, including the
    renormalised `share` key that _partition_weighted reads (shares sum to 1.0)."""
    # Dell present -> 0.80/0.20; windows alone -> 1.0 (renormalised after Dell drop).
    shares = {"dell": 0.80, "windows": 0.20} if "dell" in names else {"windows": 1.0}
    out = []
    for n in names:
        if n == "dell":
            out.append({"name": "dell", "transport": "docker_context",
                        "context": "dell", "weight": 0.80, "max_weight": 0.80,
                        "share": shares["dell"]})
        else:
            out.append({"name": "windows", "transport": "docker_local",
                        "weight": 0.20, "max_weight": 1.0,
                        "share": shares["windows"]})
    return out


class _StubRouting:
    """A routing stand-in: controlled _select_machines, REAL _partition_weighted."""

    def __init__(self, machines):
        self._machines = machines

    def _select_machines(self, cfg):
        return self._machines

    def _partition_weighted(self, items, machines):
        return routing._partition_weighted(items, machines)


class PartitionTests(unittest.TestCase):
    def test_partition_is_80_20_for_five_files(self):
        # Real Hamilton/largest-remainder: 5 files * 0.80 = 4 to dell, 1 to windows.
        split = routing._partition_weighted(
            ["a", "b", "c", "d", "e"], _machines("dell", "windows"))
        self.assertEqual(len(split["dell"]), 4)
        self.assertEqual(len(split["windows"]), 1)
        # every file assigned exactly once
        allocated = split["dell"] + split["windows"]
        self.assertCountEqual(allocated, ["a", "b", "c", "d", "e"])


class DellCommandBuilderTests(unittest.TestCase):
    def test_dell_coverage_cmd_is_a_context_run_with_volume_and_network(self):
        cmd = cov._dell_coverage_cmd(
            "dell", "apps/auto_issues/services/pgexporter_picker.py",
            ["apps/auto_issues/tests/test_pgexporter_picker.py"])
        self.assertEqual(cmd[:4], ["docker", "--context", "dell", "run"])
        joined = " ".join(cmd)
        self.assertIn(f"{cov._COVERAGE_VOLUME}:/repo", joined)
        self.assertIn("compiled_artifacts:/opt/xf/compiled", joined)
        self.assertIn("xf-internal-linker-v2_default", joined)  # compose network
        self.assertIn("DJANGO_SETTINGS_MODULE=config.settings.test", joined)
        self.assertIn("xf-linker-backend-quality:latest", cmd)


class MeasureSplitTests(unittest.TestCase):
    def _plan(self):
        return [
            ("a.py", ["test_a.py"]), ("b.py", ["test_b.py"]),
            ("c.py", ["test_c.py"]), ("d.py", ["test_d.py"]),
            ("e.py", ["test_e.py"]),
        ]

    def test_merges_dell_and_windows_results(self):
        machines = _machines("dell", "windows")
        with patch.object(cov, "_load_machine_routing",
                          return_value=_StubRouting(machines)), \
             patch.object(cov, "_load_coverage_routing_config", return_value={}), \
             patch.object(cov, "_measure_slice_on_dell") as dell, \
             patch.object(cov, "_measure_local") as local:
            # Dell handles its 4 files; Windows handles its 1 file.
            dell.side_effect = lambda ctx, sp: {rel: set() for rel, _ in sp}
            local.side_effect = lambda sp: {rel: {7} for rel, _ in sp}
            merged = cov._measure_split(self._plan())
        # all five files present in the merged map
        self.assertEqual(set(merged), {"a.py", "b.py", "c.py", "d.py", "e.py"})
        dell.assert_called_once()
        local.assert_called_once()  # only the windows slice locally
        # the one windows file has the local marker {7}
        windows_vals = [v for v in merged.values() if v == {7}]
        self.assertEqual(len(windows_vals), 1)

    def test_failopen_remeasures_locally_when_dell_slice_untrusted(self):
        machines = _machines("dell", "windows")
        with patch.object(cov, "_load_machine_routing",
                          return_value=_StubRouting(machines)), \
             patch.object(cov, "_load_coverage_routing_config", return_value={}), \
             patch.object(cov, "_measure_slice_on_dell", return_value=None) as dell, \
             patch.object(cov, "_measure_local") as local:
            local.side_effect = lambda sp: {rel: set() for rel, _ in sp}
            merged = cov._measure_split(self._plan())
        # Dell returned None (untrusted) -> its slice re-runs locally, plus the
        # windows slice locally => _measure_local called twice, all files present.
        self.assertEqual(set(merged), {"a.py", "b.py", "c.py", "d.py", "e.py"})
        dell.assert_called_once()
        self.assertEqual(local.call_count, 2)

    def test_failopen_all_local_when_no_dell_machine(self):
        machines = _machines("windows")  # Dell dropped by probe
        with patch.object(cov, "_load_machine_routing",
                          return_value=_StubRouting(machines)), \
             patch.object(cov, "_load_coverage_routing_config", return_value={}), \
             patch.object(cov, "_measure_slice_on_dell") as dell, \
             patch.object(cov, "_measure_local") as local:
            local.side_effect = lambda sp: {rel: set() for rel, _ in sp}
            merged = cov._measure_split(self._plan())
        dell.assert_not_called()
        local.assert_called_once()
        self.assertEqual(set(merged), {"a.py", "b.py", "c.py", "d.py", "e.py"})


class MeasureMissingMapGatingTests(unittest.TestCase):
    def test_uses_split_when_flag_set(self):
        prod = ["backend/apps/x/services/foo.py"]
        with patch.dict(os.environ, {"XF_COVERAGE_SPLIT": "1"}), \
             patch.object(cov, "_test_paths_for", return_value=["t.py"]), \
             patch.object(cov, "_measure_split",
                          return_value={"apps/x/services/foo.py": set()}) as sp, \
             patch.object(cov, "_measure_local") as loc:
            result = cov._measure_missing_map(prod)
        sp.assert_called_once()
        loc.assert_not_called()
        self.assertIn("backend/apps/x/services/foo.py", result)

    def test_uses_local_when_flag_unset(self):
        prod = ["backend/apps/x/services/foo.py"]
        env = {k: v for k, v in os.environ.items() if k != "XF_COVERAGE_SPLIT"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(cov, "_test_paths_for", return_value=["t.py"]), \
             patch.object(cov, "_measure_split") as sp, \
             patch.object(cov, "_measure_local",
                          return_value={"apps/x/services/foo.py": set()}) as loc:
            cov._measure_missing_map(prod)
        loc.assert_called_once()
        sp.assert_not_called()


class VerifySnapshotTests(unittest.TestCase):
    def test_true_when_every_hash_matches(self):
        host = {"a.py": "h1", "b.py": "h2"}

        def run_remote(rel_slice):
            return 0, "h1  a.py\nh2  b.py\n"

        self.assertTrue(cov._verify_dell_snapshot(run_remote, ["a.py", "b.py"], host))

    def test_false_when_a_hash_differs(self):
        host = {"a.py": "h1", "b.py": "h2"}

        def run_remote(rel_slice):
            return 0, "h1  a.py\nWRONG  b.py\n"

        self.assertFalse(cov._verify_dell_snapshot(run_remote, ["a.py", "b.py"], host))

    def test_false_when_remote_command_fails(self):
        self.assertFalse(
            cov._verify_dell_snapshot(lambda s: (1, "err"), ["a.py"], {"a.py": "h"}))


class ConfigTests(unittest.TestCase):
    def test_fallback_is_dell_80_windows_20(self):
        with patch.object(cov.Path, "read_text", return_value="{}"):
            cfg = cov._load_coverage_routing_config()
        # Returns a cfg dict shaped for _select_machines (a "machines" key).
        machines = cfg["machines"]
        by_name = {m["name"]: m for m in machines}
        self.assertAlmostEqual(by_name["dell"]["weight"], 0.80)
        self.assertAlmostEqual(by_name["windows"]["weight"], 0.20)
        self.assertEqual(by_name["dell"]["transport"], "docker_context")


class ParseMissingTests(unittest.TestCase):
    def test_extracts_missing_line_numbers(self):
        report = (
            "Name                Stmts   Miss  Cover   Missing\n"
            "apps/x/foo.py          10      2    80%   12, 15-16\n"
        )
        missing = cov._parse_missing(report, "apps/x/foo.py")
        self.assertEqual(missing, {12, 15, 16})

    def test_none_when_file_absent_from_report(self):
        self.assertIsNone(cov._parse_missing("no rows here", "apps/x/foo.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
