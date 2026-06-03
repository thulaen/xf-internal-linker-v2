"""Tests for scripts/sync_agent_rules.py CLI return codes.

BDD:
  Given diff_shared_sections reports errors
  When check() runs
  Then it returns exit code 1; with no errors it returns 0

  Given a required plan phrase missing from one agent file
  When verify_plan_rules() runs
  Then it returns 1 and names the missing item
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "sync_agent_rules.py"


def _load():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("sync_agent_rules", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_agent_rules"] = mod
    spec.loader.exec_module(mod)
    return mod


s = _load()


class TestCheck(TestCase):
    def test_returns_zero_when_no_errors(self) -> None:
        with mock.patch.object(s, "load_manifest", return_value={}), mock.patch.object(
            s, "diff_shared_sections", return_value=[]
        ):
            self.assertEqual(s.check(), 0)

    def test_returns_one_when_errors(self) -> None:
        with mock.patch.object(s, "load_manifest", return_value={}), mock.patch.object(
            s, "diff_shared_sections", return_value=["mismatch in AGENTS.md"]
        ):
            self.assertEqual(s.check(), 1)


class TestVerifyPlanRules(TestCase):
    def test_zero_when_all_present(self) -> None:
        manifest = {"plan_40_41_42_required": ["RULE-X"]}
        with mock.patch.object(s, "load_manifest", return_value=manifest), mock.patch.object(
            s, "read_agent_files", return_value={"AGENTS.md": "has RULE-X here"}
        ):
            self.assertEqual(s.verify_plan_rules(), 0)

    def test_one_when_missing(self) -> None:
        manifest = {"plan_40_41_42_required": ["RULE-X"]}
        with mock.patch.object(s, "load_manifest", return_value=manifest), mock.patch.object(
            s, "read_agent_files", return_value={"AGENTS.md": "nothing"}
        ):
            self.assertEqual(s.verify_plan_rules(), 1)


class TestVerifyForbiddenPhrases(TestCase):
    def test_zero_when_all_phrases_present(self) -> None:
        manifest = {"forbidden_phrases": ["bad phrase"]}
        with mock.patch.object(s, "load_manifest", return_value=manifest), mock.patch.object(
            s, "read_agent_files", return_value={"AGENTS.md": "lists bad phrase"}
        ):
            self.assertEqual(s.verify_forbidden_phrases(), 0)

    def test_one_when_phrase_absent(self) -> None:
        manifest = {"forbidden_phrases": ["bad phrase"]}
        with mock.patch.object(s, "load_manifest", return_value=manifest), mock.patch.object(
            s, "read_agent_files", return_value={"AGENTS.md": "clean"}
        ):
            self.assertEqual(s.verify_forbidden_phrases(), 1)


class TestMainDispatch(TestCase):
    def test_check_flag_calls_check(self) -> None:
        with mock.patch.object(s, "check", return_value=0) as chk:
            self.assertEqual(s.main(["--check"]), 0)
        chk.assert_called_once()

    def test_apply_flag_calls_apply_from(self) -> None:
        with mock.patch.object(s, "apply_from", return_value=0) as ap:
            self.assertEqual(s.main(["--apply", "AGENTS.md"]), 0)
        ap.assert_called_once_with("AGENTS.md")

    def test_no_flag_errors(self) -> None:
        with self.assertRaises(SystemExit):
            s.main([])
