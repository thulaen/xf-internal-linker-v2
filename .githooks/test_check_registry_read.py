"""Tests for `check-registry-read.py` (the auto-fix-30 guard).

Runnable on the host without Django or Docker:

    python -m unittest .githooks.test_check_registry_read
    python .githooks/test_check_registry_read.py

The hook validates the ten-source marker, 30 real picked AutoIssue IDs,
and the drought-substitution clause. Satisfier phrases are intentionally
rejected because every session must pick 30 real issue IDs.
"""

from __future__ import annotations

import importlib.util
import unittest
from subprocess import CalledProcessError
from pathlib import Path
from unittest import mock

_HOOK_PATH = Path(__file__).resolve().parent / "check-registry-read.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "check_registry_read_hook", _HOOK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ids(prefix: str, count: int) -> str:
    """Render `#prefix1, #prefix2, ...` for `count` IDs."""
    return ", ".join(f"#{prefix}{i}" for i in range(1, count + 1))


def _valid_ten_source_marker(
    *,
    a: int = 3,
    g: int = 3,
    p: int = 3,
    t: int = 3,
    l: int = 3,
    f: int = 3,
    m: int = 3,
    z: int = 3,
    c: int = 3,
    gh: int = 3,
    picks_a: int = 3,
    picks_g: int = 3,
    picks_p: int = 3,
    picks_t: int = 3,
    picks_l: int = 3,
    picks_f: int = 3,
    picks_m: int = 3,
    picks_z: int = 3,
    picks_c: int = 3,
    picks_gh: int = 3,
    extra_phrase: str = "",
) -> str:
    n = a + g + p + t + l + f + m + z + c + gh
    picks = (
        f"picked: {_ids('a', picks_a)} | g: {_ids('g', picks_g)} "
        f"| p: {_ids('p', picks_p)} | t: {_ids('t', picks_t)} "
        f"| l: {_ids('l', picks_l)} | f: {_ids('f', picks_f)} "
        f"| m: {_ids('m', picks_m)} | z: {_ids('z', picks_z)} "
        f"| c: {_ids('c', picks_c)} | gh: {_ids('gh', picks_gh)}"
    )
    return (
        f"[REGISTRY READ: {n} open ({a} agent / {g} glitchtip / "
        f"{p} pyroscope / {t} tempo / {l} loki / {f} faro / "
        f"{m} mutation / {z} fuzz / {c} contract / {gh} gh_ci), "
        f"6 registry - {picks}]{extra_phrase}"
    )


class CheckRegistryReadHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_pre_2026_05_10_legacy_marker_rejected(self):
        added = (
            "[REGISTRY READ: 4 open auto-issues, 0 registry - "
            "picked: #1, #2, #3]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_four_source_12_pick_marker_rejected(self):
        added = (
            "[REGISTRY READ: 12 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 2 loki), 4 registry - picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 | l: #9, #10, #11, #12]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_ten_source_marker_with_correct_sum_accepted(self):
        added = _valid_ten_source_marker(g=4, t=2, gh=5)
        self.assertEqual(self.hook._validate_marker(added), 0)

    def test_ten_source_marker_mismatched_sum_rejected(self):
        added = (
            "[REGISTRY READ: 31 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "3 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
            "3 gh_ci), 6 registry - picked: #1]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_no_marker_rejected(self):
        added = "Some random commit body without a marker."
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_thirty_picks_accepted(self):
        added = _valid_ten_source_marker()
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_twenty_nine_picks_rejected(self):
        added = _valid_ten_source_marker(picks_gh=2)
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_all_satisfier_phrases_rejected(self):
        phrases = (
            "auto-fix-30 satisfier",
            "auto-fix-18 satisfier",
            "auto-fix-12 satisfier",
            "auto-fix-3 satisfier",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                added = _valid_ten_source_marker(extra_phrase=f" {phrase}")
                self.assertEqual(self.hook._validate_picks(added), 1)

    def test_marker_without_picked_ids_rejects_satisfier_shortcut(self):
        added = (
            "[REGISTRY READ: 30 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "3 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
            "3 gh_ci), 6 registry - auto-fix-30 satisfier]"
        )
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_marker_without_picked_ids_rejected(self):
        added = (
            "[REGISTRY READ: 30 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "3 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
            "3 gh_ci), 6 registry]"
        )
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_drought_in_tempo_bucket_with_phrase_accepted(self):
        added = (
            "[REGISTRY READ: 27 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "0 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
            "3 gh_ci), 6 registry - "
            "picked: #a1, #a2, #a3 | g: #g1, #g2, #g3 "
            "| p: #p1, #p2, #p3 "
            "| t: 0 found + 3 from agent: #t1, #t2, #t3 (drought logged: #99) "
            "| l: #l1, #l2, #l3 | f: #f1, #f2, #f3 "
            "| m: #m1, #m2, #m3 | z: #z1, #z2, #z3 "
            "| c: #c1, #c2, #c3 | gh: #gh1, #gh2, #gh3]"
        )
        self.assertEqual(self.hook._validate_marker(added), 0)
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_drought_substitution_without_phrase_rejected(self):
        added = (
            "[REGISTRY READ: 27 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "0 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
            "3 gh_ci), 6 registry - "
            "picked: #a1, #a2, #a3 | g: #g1, #g2, #g3 "
            "| p: #p1, #p2, #p3 "
            "| t: 0 found + 3 from agent: #t1, #t2, #t3 "
            "| l: #l1, #l2, #l3 | f: #f1, #f2, #f3 "
            "| m: #m1, #m2, #m3 | z: #z1, #z2, #z3 "
            "| c: #c1, #c2, #c3 | gh: #gh1, #gh2, #gh3]"
        )
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_required_session_markers_accepted(self):
        added = (
            "[CI FAILED RUNS READ: skipped - gh unavailable]\n"
            "[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]\n"
            "[COVERAGE GAPS READ: 10 picked - #1, #2, #3]\n"
            "[COVERAGE SUMMARY: target=90% actual=91.5% - met]"
        )
        self.assertEqual(self.hook._validate_ci_failed_runs(added), 0)
        self.assertEqual(self.hook._validate_guidelines_read(added), 0)
        self.assertEqual(self.hook._validate_coverage_gaps(added), 0)
        self.assertEqual(self.hook._validate_coverage_summary(added), 0)

    def test_required_session_markers_rejected_when_missing(self):
        added = "no session markers here"
        self.assertEqual(self.hook._validate_ci_failed_runs(added), 1)
        self.assertEqual(self.hook._validate_guidelines_read(added), 1)
        self.assertEqual(self.hook._validate_coverage_gaps(added), 1)
        self.assertEqual(self.hook._validate_coverage_summary(added), 1)

    def test_staged_diff_filters_added_lines(self):
        diff = (
            "diff --git a/AGENT-HANDOFF.md b/AGENT-HANDOFF.md\n"
            "+++ b/AGENT-HANDOFF.md\n"
            "+[REGISTRY READ: 30 open]\n"
            "+plain addition\n"
            " context line\n"
        )
        with mock.patch.object(self.hook.subprocess, "check_output", return_value=diff):
            result = self.hook._staged_diff_for(self.hook.HANDOFF)
        self.assertEqual(result, "[REGISTRY READ: 30 open]\nplain addition")

    def test_staged_diff_returns_empty_on_git_error(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            side_effect=CalledProcessError(1, "git"),
        ):
            self.assertEqual(self.hook._staged_diff_for(self.hook.HANDOFF), "")

    def test_commit_touches_handoff(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            return_value="AGENT-HANDOFF.md\nREADME.md\n",
        ):
            self.assertTrue(self.hook._commit_touches_handoff())

    def test_commit_does_not_touch_handoff(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            return_value="README.md\n",
        ):
            self.assertFalse(self.hook._commit_touches_handoff())

    def test_commit_touches_handoff_returns_false_on_git_error(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            side_effect=CalledProcessError(1, "git"),
        ):
            self.assertFalse(self.hook._commit_touches_handoff())

    def test_main_skips_when_handoff_unchanged(self):
        with mock.patch.object(self.hook, "_commit_touches_handoff", return_value=False):
            self.assertEqual(self.hook.main(), 0)

    def test_main_accepts_complete_handoff_markers(self):
        added = (
            _valid_ten_source_marker()
            + "\n[CI FAILED RUNS READ: skipped - gh unavailable]"
            + "\n[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]"
            + "\n[COVERAGE GAPS READ: 10 picked - #1, #2, #3]"
            + "\n[COVERAGE SUMMARY: target=90% actual=91% - met]"
        )
        with (
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=True),
            mock.patch.object(self.hook, "_staged_diff_for", return_value=added),
        ):
            self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main()
