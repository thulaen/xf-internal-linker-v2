"""Tests for scripts/scope_cap.py.

BDD:
  Given a scope larger than the cap and no CI opt-in
  When enforce_cap() runs
  Then it raises ScopeCapExceeded with an exact failure message

  Given XF_QUALITY_ENV=ci and XF_SCOPE_FULL_TREE=1
  When enforce_cap() runs on an over-cap scope
  Then it returns the cleaned scope (full-tree opt-in)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "scope_cap.py"


def _load():
    spec = importlib.util.spec_from_file_location("scope_cap", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scope_cap"] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load()


class TestFormatFailure(TestCase):
    def test_exact_failure_text(self) -> None:
        msg = sc.format_failure("ruff", 12, 5)
        self.assertEqual(
            msg,
            "FAIL scope cap: ruff targets=12 cap=5.\n"
            "UNBLOCK: narrow the commit, increase cap with documented reason, "
            "or move whole-tree run to CI (XF_QUALITY_ENV=ci).",
        )


class TestCiOptIn(TestCase):
    def test_true_only_when_both_vars_set(self) -> None:
        self.assertTrue(
            sc.ci_full_tree_opted_in(
                {"XF_QUALITY_ENV": "ci", "XF_SCOPE_FULL_TREE": "1"}
            )
        )

    def test_false_when_env_not_ci(self) -> None:
        self.assertFalse(
            sc.ci_full_tree_opted_in(
                {"XF_QUALITY_ENV": "local", "XF_SCOPE_FULL_TREE": "1"}
            )
        )

    def test_false_when_full_tree_not_one(self) -> None:
        self.assertFalse(
            sc.ci_full_tree_opted_in(
                {"XF_QUALITY_ENV": "ci", "XF_SCOPE_FULL_TREE": "0"}
            )
        )

    def test_false_when_empty(self) -> None:
        self.assertFalse(sc.ci_full_tree_opted_in({}))


class TestEnforceCap(TestCase):
    def test_returns_clean_scope_when_within_cap(self) -> None:
        result = sc.enforce_cap(["a.py", "", "b.py"], 5, "ruff", env={})
        self.assertEqual(result, ["a.py", "b.py"])

    def test_boundary_equal_to_cap_is_allowed(self) -> None:
        result = sc.enforce_cap(["a", "b", "c"], 3, "ruff", env={})
        self.assertEqual(result, ["a", "b", "c"])

    def test_one_over_cap_raises(self) -> None:
        with self.assertRaises(sc.ScopeCapExceeded) as ctx:
            sc.enforce_cap(["a", "b", "c", "d"], 3, "ruff", env={})
        self.assertEqual(ctx.exception.count, 4)
        self.assertEqual(ctx.exception.cap, 3)
        self.assertEqual(ctx.exception.tool, "ruff")

    def test_ci_opt_in_bypasses_cap(self) -> None:
        result = sc.enforce_cap(
            ["a", "b", "c", "d"],
            1,
            "ruff",
            env={"XF_QUALITY_ENV": "ci", "XF_SCOPE_FULL_TREE": "1"},
        )
        self.assertEqual(result, ["a", "b", "c", "d"])
