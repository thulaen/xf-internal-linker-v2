"""Tests for scripts/turbo_mutation.py pure helpers.

BDD:
  Given a core count and a machine share
  When _jobs_for() runs
  Then it returns round(cores*share) with a floor of 1

  Given split:false for a language
  When _machines_for_language() runs
  Then it returns a Windows-only machine list (no fan-out)

  Given a report path that does not exist
  When _file_survivors() runs
  Then it returns a "no report" message and never shells out
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "turbo_mutation.py"


def _load():
    spec = importlib.util.spec_from_file_location("turbo_mutation", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["turbo_mutation"] = mod
    spec.loader.exec_module(mod)
    return mod


tm = _load()


class TestJobsFor(TestCase):
    def test_rounds_cores_times_share(self) -> None:
        self.assertEqual(tm._jobs_for(10, 0.6), 6)

    def test_floors_at_one(self) -> None:
        self.assertEqual(tm._jobs_for(2, 0.1), 1)

    def test_zero_cores_floors_at_one(self) -> None:
        self.assertEqual(tm._jobs_for(0, 0.5), 1)

    def test_rounds_to_nearest(self) -> None:
        self.assertEqual(tm._jobs_for(7, 0.5), 4)  # round(3.5) -> 4 banker's? py rounds to even


class TestMachinesForLanguage(TestCase):
    def test_split_false_is_windows_only(self) -> None:
        machines = tm._machines_for_language({}, split_enabled=False)
        self.assertEqual(len(machines), 1)
        self.assertEqual(machines[0]["name"], "windows")
        self.assertEqual(machines[0]["share"], 1.0)

    def test_split_true_delegates_to_select_machines(self) -> None:
        sentinel = [{"name": "dell"}]
        with mock.patch.object(tm, "_select_machines", return_value=sentinel) as sel:
            machines = tm._machines_for_language({"cfg": 1}, split_enabled=True)
        sel.assert_called_once()
        self.assertEqual(machines, sentinel)


class TestWriteJsonBlob(TestCase):
    def test_writes_valid_json_object(self) -> None:
        target = mock.Mock()
        tm._write_json_blob('noise before {"a": 1}', target)
        target.write_text.assert_called_once()
        self.assertIn('{"a": 1}', target.write_text.call_args[0][0])

    def test_ignores_trailing_text_after_json(self) -> None:
        target = mock.Mock()
        tm._write_json_blob('{"a": 1} trailing junk', target)
        target.write_text.assert_not_called()

    def test_ignores_invalid_json(self) -> None:
        target = mock.Mock()
        tm._write_json_blob("no brace here", target)
        target.write_text.assert_not_called()


class TestFileSurvivors(TestCase):
    def test_no_report_skips_filing(self) -> None:
        report = mock.Mock()
        report.is_file.return_value = False
        out = tm._file_survivors("mutmut", report, dry_run=False)
        self.assertIn("no report", out)

    def test_dry_run_does_not_shell(self) -> None:
        report = mock.Mock()
        report.is_file.return_value = True
        with mock.patch.object(tm.subprocess, "run") as run:
            out = tm._file_survivors("mutmut", report, dry_run=True)
        run.assert_not_called()
        self.assertIn("dry-run", out)


class TestMachineCores(TestCase):
    def test_override_wins(self) -> None:
        self.assertEqual(
            tm._machine_cores({"transport": "ssh"}, override=12), 12
        )

    def test_ssh_default_is_twenty(self) -> None:
        self.assertEqual(
            tm._machine_cores({"transport": "ssh"}, override=0), 20
        )

    def test_local_probes_docker_cores(self) -> None:
        with mock.patch.object(tm, "_docker_cores", return_value=6) as probe:
            cores = tm._machine_cores({"transport": "docker_local"}, override=0)
        probe.assert_called_once_with("local")
        self.assertEqual(cores, 6)
