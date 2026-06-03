"""Tests for scripts/turbo_tests.py pure helpers.

BDD:
  Given a machine with an unknown transport
  When _run_shard_on_machine() runs
  Then it returns rc=1 and a "shard skipped" message (never silently passes)

  Given a shard result whose rc is None (thread crashed)
  When _merge_shard_results() runs
  Then it re-runs that shard locally before deciding the final return code
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "turbo_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("turbo_tests", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["turbo_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


tt = _load()


class TestRunShardOnMachine(TestCase):
    def test_docker_local_dispatches_local(self) -> None:
        with mock.patch.object(
            tt, "_run_shard_local", return_value=(0, "ok")
        ) as local:
            rc, out = tt._run_shard_on_machine(
                {"transport": "docker_local", "name": "windows"}, ["a.py"]
            )
        local.assert_called_once()
        self.assertEqual(rc, 0)

    def test_docker_context_dispatches_context(self) -> None:
        with mock.patch.object(
            tt, "_run_shard_context", return_value=(0, "ok")
        ) as ctx:
            tt._run_shard_on_machine(
                {"transport": "docker_context", "name": "mint", "context": "mint"},
                ["a.py"],
            )
        ctx.assert_called_once()

    def test_unknown_transport_returns_skip(self) -> None:
        rc, out = tt._run_shard_on_machine(
            {"transport": "carrier-pigeon", "name": "weird"}, ["a.py"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("Unknown transport", out)


class TestMergeShardResults(TestCase):
    def test_all_pass_returns_zero(self) -> None:
        results = [
            {"machine": {"name": "w"}, "rc": 0},
            {"machine": {"name": "m"}, "rc": 0},
        ]
        self.assertEqual(tt._merge_shard_results(results), 0)

    def test_any_failure_returns_one(self) -> None:
        results = [
            {"machine": {"name": "w"}, "rc": 0},
            {"machine": {"name": "m"}, "rc": 2},
        ]
        self.assertEqual(tt._merge_shard_results(results), 1)

    def test_none_rc_triggers_local_rerun(self) -> None:
        results = [{"machine": {"name": "w"}, "rc": None, "files": ["a.py"], "cmd": ""}]
        with mock.patch.object(
            tt, "_run_shard_local", return_value=(0, "rerun ok")
        ) as rerun:
            final = tt._merge_shard_results(results)
        rerun.assert_called_once_with(["a.py"], "")
        self.assertEqual(final, 0)

    def test_none_rc_rerun_failure_returns_one(self) -> None:
        results = [{"machine": {"name": "w"}, "rc": None, "files": ["a.py"], "cmd": ""}]
        with mock.patch.object(tt, "_run_shard_local", return_value=(1, "rerun bad")):
            self.assertEqual(tt._merge_shard_results(results), 1)


class TestConstants(TestCase):
    def test_test_volume_name(self) -> None:
        self.assertEqual(tt._TEST_VOLUME, "xf_test_repo")
