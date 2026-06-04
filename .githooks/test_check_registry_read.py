"""Tests for `check-registry-read.py` (the auto-fix-30 guard).

Runnable on the host without Django or Docker:

    python -m unittest .githooks.test_check_registry_read
    python .githooks/test_check_registry_read.py

The hook validates the ten-source marker, 30 real picked AutoIssue IDs,
the drought-substitution clause, and the quality markers required for
code commits. Satisfier phrases are intentionally rejected because every
session must pick 30 real issue IDs.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from io import StringIO
from subprocess import CalledProcessError, CompletedProcess
from pathlib import Path
from unittest import mock

_HOOK_PATH = Path(__file__).resolve().parent / "check-registry-read.py"
_REPO_ROOT = _HOOK_PATH.parents[1]


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
    loki: int = 3,
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
    n = a + g + p + t + loki + f + m + z + c + gh
    picks = (
        f"picked: {_ids('a', picks_a)} | g: {_ids('g', picks_g)} "
        f"| p: {_ids('p', picks_p)} | t: {_ids('t', picks_t)} "
        f"| l: {_ids('l', picks_l)} | f: {_ids('f', picks_f)} "
        f"| m: {_ids('m', picks_m)} | z: {_ids('z', picks_z)} "
        f"| c: {_ids('c', picks_c)} | gh: {_ids('gh', picks_gh)}"
    )
    return (
        f"[REGISTRY READ: {n} open ({a} agent / {g} glitchtip / "
        f"{p} pyroscope / {t} tempo / {loki} loki / {f} faro / "
        f"{m} mutation / {z} fuzz / {c} contract / {gh} gh_ci), "
        f"6 registry - {picks}]{extra_phrase}"
    )


def _valid_numeric_ten_source_marker() -> str:
    ids = iter(range(1, 31))
    parts = []
    for label in ("picked", "g", "p", "t", "l", "f", "m", "z", "c", "gh"):
        prefix = "picked: " if label == "picked" else f"| {label}: "
        parts.append(prefix + ", ".join(f"#{next(ids)}" for _ in range(3)))
    return (
        "[REGISTRY READ: 30 open (3 agent / 3 glitchtip / 3 pyroscope / "
        "3 tempo / 3 loki / 3 faro / 3 mutation / 3 fuzz / 3 contract / "
        f"3 gh_ci), 6 registry - {' '.join(parts)}]"
    )


def _zero_open_ten_source_marker() -> str:
    return (
        "[REGISTRY READ: 0 open (0 agent / 0 glitchtip / 0 pyroscope / "
        "0 tempo / 0 loki / 0 faro / 0 mutation / 0 fuzz / 0 contract / "
        "0 gh_ci), 0 registry - picked: none]"
    )


def _quality_read_marker() -> str:
    return (
        "[QUALITY GATE READ: self-written code must pass guidelines, tests, "
        "coverage, mutation tests, and required check setup before commit]"
    )


def _quality_result_marker(**overrides: str) -> str:
    values = {
        "guidelines": "passed",
        "tests": "passed",
        "coverage": "met",
        "mutation": "passed",
        "check_setup": "passed",
    }
    values.update(overrides)
    return (
        "[QUALITY GATE RESULT: "
        f"guidelines={values['guidelines']} "
        f"tests={values['tests']} "
        f"coverage={values['coverage']} "
        f"mutation={values['mutation']} "
        f"check_setup={values['check_setup']}]"
    )


def _self_review_marker(**overrides: str) -> str:
    values = {
        "scope": "task-files",
        "autoissues": "none",
        "fixes": "none",
        "reuse": "passed",
        "shared_library": "passed",
        "complexity": "passed",
        "tests": "passed",
        "coverage": "met",
        "mutation": "passed-or-not-required",
        "benchmark": "passed-or-not-required",
        "edge_cases": "covered",
        "issues": "fixed-or-none",
    }
    values.update(overrides)
    body = " ".join(f"{key}={value}" for key, value in values.items())
    return f"[SELF REVIEW RESULT: {body}]"


def _bdd_marker() -> str:
    return (
        "[BDD PROOF: Given code changes are staged When the handoff is written "
        "Then the user-facing behavior is described in plain English]"
    )


def _tdd_marker(**overrides: str) -> str:
    values = {
        "before_or_alongside": "yes",
        "tests": "python .githooks/test_check_registry_read.py",
        "result": "passed",
    }
    values.update(overrides)
    body = " ".join(f"{key}={value}" for key, value in values.items())
    return f"[TDD PROOF: {body}]"


def _lesson_read_marker() -> str:
    return "[RESOLVED HISTORY: 2 prior fix(es) read in .githooks]"


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

    def test_six_source_pre_phase_6_marker_rejected(self):
        """AutoIssue #205 — the pre-Phase-6 6-source marker must be
        rejected because Live total cannot equal the bucket sum after
        Phase 6 added mutation/fuzz/contract/gh_ci sources.
        """
        added = (
            "[REGISTRY READ: 18 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "3 tempo / 3 loki / 3 faro), 0 registry - picked: "
            "#1, #2, #3 | g: #4, #5, #6 | p: #7, #8, #9 | t: #10, #11, #12 "
            "| l: #13, #14, #15 | f: #16, #17, #18]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_ten_source_marker_with_correct_sum_accepted(self):
        added = _valid_ten_source_marker(g=4, t=2, gh=5)
        self.assertEqual(self.hook._validate_marker(added), 0)

    def test_zero_open_ten_source_marker_accepted(self):
        added = _zero_open_ten_source_marker()
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

    def test_zero_open_marker_accepts_zero_picks(self):
        added = _zero_open_ten_source_marker()
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_twenty_nine_picks_rejected(self):
        added = _valid_ten_source_marker(picks_gh=2)
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_duplicate_picked_id_rejected(self):
        added = _valid_numeric_ten_source_marker().replace("#2", "#1", 1)
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
        self.assertNotIn("99", self.hook._extract_picked_issue_ids(added))
        self.assertEqual(len(self.hook._extract_picked_issue_ids(added)), 30)

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

    def test_code_commit_without_quality_gate_read_marker_fails(self):
        added = _quality_result_marker()
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(
                added,
                [".githooks/check-registry-read.py"],
            ),
            1,
        )

    def test_code_commit_without_quality_gate_result_marker_fails(self):
        added = _quality_read_marker()
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(
                added,
                [".githooks/check-registry-read.py"],
            ),
            1,
        )

    def test_quality_gate_coverage_not_met_fails(self):
        added = _quality_read_marker() + "\n" + _quality_result_marker(coverage="not met")
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(added, ["backend/apps/core/foo.py"]),
            1,
        )

    def test_quality_gate_mutation_skipped_fails(self):
        added = _quality_read_marker() + "\n" + _quality_result_marker(mutation="skipped")
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(added, ["frontend/src/app/foo.ts"]),
            1,
        )

    def test_quality_gate_check_setup_missing_tool_fails(self):
        added = _quality_read_marker() + "\n" + _quality_result_marker(
            check_setup="missing tool"
        )
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(added, ["backend/apps/core/foo.py"]),
            1,
        )

    def test_quality_gate_tests_not_run_fails(self):
        added = _quality_read_marker() + "\n" + _quality_result_marker(tests="not run")
        self.assertEqual(
            self.hook._validate_quality_gate_for_code(added, ["backend/apps/core/foo.py"]),
            1,
        )

    def test_docs_only_commit_with_not_applicable_passes(self):
        added = (
            _quality_read_marker()
            + "\n"
            + _quality_result_marker(
                guidelines="not applicable",
                tests="not applicable",
                coverage="not applicable",
                mutation="not applicable",
                check_setup="not applicable",
            )
        )
        self.assertEqual(self.hook._validate_quality_gate_for_code(added, []), 0)

    def test_code_commit_without_self_review_marker_fails(self):
        with mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(
                self.hook._validate_self_review_for_code(
                    "no self review",
                    ["backend/apps/core/foo.py"],
                ),
                1,
            )
        msg = err.getvalue()
        for required in (
            "bugs",
            "silent errors",
            "correctness",
            "tech debt",
            "maintainability",
            "duplication",
            "long functions",
        ):
            self.assertIn(required, msg)

    def test_self_review_marker_with_missing_fields_fails(self):
        added = "[SELF REVIEW RESULT: scope=task-files issues=none]"
        self.assertEqual(
            self.hook._validate_self_review_for_code(
                added,
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_self_review_marker_accepts_scoped_review_result(self):
        self.assertEqual(
            self.hook._validate_self_review_for_code(
                _self_review_marker(),
                ["backend/apps/core/foo.py"],
            ),
            0,
        )

    def test_docs_only_commit_does_not_require_self_review_marker(self):
        self.assertEqual(self.hook._validate_self_review_for_code("", []), 0)

    def test_code_commit_without_bdd_proof_marker_fails(self):
        self.assertEqual(
            self.hook._validate_bdd_proof_for_code(
                "no bdd proof",
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_bdd_proof_without_given_when_then_fails(self):
        added = "[BDD PROOF: code was tested]"
        self.assertEqual(
            self.hook._validate_bdd_proof_for_code(
                added,
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_bdd_proof_with_given_when_then_passes(self):
        self.assertEqual(
            self.hook._validate_bdd_proof_for_code(
                _bdd_marker(),
                ["backend/apps/core/foo.py"],
            ),
            0,
        )

    def test_code_commit_without_tdd_proof_marker_fails(self):
        self.assertEqual(
            self.hook._validate_tdd_proof_for_code(
                "no tdd proof",
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_tdd_proof_with_missing_fields_fails(self):
        added = "[TDD PROOF: tests=python .githooks/test_check_registry_read.py]"
        self.assertEqual(
            self.hook._validate_tdd_proof_for_code(
                added,
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_tdd_proof_with_failed_result_fails(self):
        self.assertEqual(
            self.hook._validate_tdd_proof_for_code(
                _tdd_marker(result="failed"),
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_tdd_proof_with_passing_result_passes(self):
        self.assertEqual(
            self.hook._validate_tdd_proof_for_code(
                _tdd_marker(),
                ["backend/apps/core/foo.py"],
            ),
            0,
        )

    def test_code_commit_without_autoissue_lesson_read_fails(self):
        self.assertEqual(
            self.hook._validate_lesson_read_for_code(
                "no resolved history",
                ["backend/apps/core/foo.py"],
            ),
            1,
        )

    def test_code_commit_with_autoissue_lesson_read_passes(self):
        self.assertEqual(
            self.hook._validate_lesson_read_for_code(
                _lesson_read_marker(),
                ["backend/apps/core/foo.py"],
            ),
            0,
        )

    def test_hook_python_changes_count_as_code(self):
        with mock.patch.object(
            self.hook,
            "_staged_files",
            return_value=[".githooks/check-registry-read.py", "AGENT-HANDOFF.md"],
        ):
            self.assertEqual(
                self.hook._staged_code_files(),
                [".githooks/check-registry-read.py"],
            )

    def test_staged_files_returns_names_and_ignores_blank_lines(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            return_value="backend/apps/core/foo.py\n\nAGENT-HANDOFF.md\n",
        ):
            self.assertEqual(
                self.hook._staged_files(),
                ["backend/apps/core/foo.py", "AGENT-HANDOFF.md"],
            )

    def test_staged_files_returns_empty_on_git_error(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            side_effect=CalledProcessError(1, "git"),
        ):
            self.assertEqual(self.hook._staged_files(), [])

    def test_githook_non_markdown_file_counts_as_code(self):
        self.assertTrue(self.hook._is_code_file(".githooks/pre-push"))

    def test_generated_build_folder_is_blocked(self):
        self.assertTrue(
            self.hook._is_generated_build_file(
                "backend/extensions/build_tests/test_simsearch.vcxproj"
            )
        )

    def test_compiled_binary_is_blocked(self):
        self.assertTrue(
            self.hook._is_generated_build_file(
                "backend/extensions/scoring.cpython-312-x86_64-linux-gnu.so"
            )
        )

    def test_source_file_is_not_generated_build_output(self):
        self.assertFalse(self.hook._is_generated_build_file("backend/extensions/scoring.cpp"))

    def test_staged_generated_build_files_are_rejected(self):
        with mock.patch.object(
            self.hook,
            "_staged_generated_build_files",
            return_value=["backend/extensions/scoring.cpython-312-x86_64-linux-gnu.so"],
        ):
            self.assertEqual(self.hook._validate_no_generated_build_files(), 1)

    def test_no_staged_generated_build_files_allows_commit_check_to_continue(self):
        with mock.patch.object(
            self.hook,
            "_staged_generated_build_files",
            return_value=[],
        ):
            self.assertEqual(self.hook._validate_no_generated_build_files(), 0)

    def test_temporary_test_artifact_folder_is_blocked(self):
        self.assertTrue(
            self.hook._is_temporary_test_artifact(".pytest_cache/v/cache/nodeids")
        )

    def test_temporary_test_artifact_file_is_blocked(self):
        self.assertTrue(self.hook._is_temporary_test_artifact("coverage.xml"))

    def test_quality_evidence_summary_is_not_temporary_artifact(self):
        self.assertFalse(
            self.hook._is_temporary_test_artifact(
                "backend/reports/quality-evidence/quality-debt.jsonl"
            )
        )

    def test_staged_temporary_test_artifacts_are_rejected(self):
        with mock.patch.object(
            self.hook,
            "_staged_temporary_test_artifacts",
            return_value=[".pytest_cache/v/cache/nodeids"],
        ):
            self.assertEqual(self.hook._validate_no_temporary_test_artifacts(), 1)

    def test_no_staged_temporary_test_artifacts_allows_commit_check_to_continue(self):
        with mock.patch.object(
            self.hook,
            "_staged_temporary_test_artifacts",
            return_value=[],
        ):
            self.assertEqual(self.hook._validate_no_temporary_test_artifacts(), 0)

    def test_unstaged_session_files_reads_git_diff(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            return_value="AI-CONTEXT.md\nREADME.md\nAGENT-HANDOFF.md\n",
        ):
            self.assertEqual(
                self.hook._unstaged_session_files(),
                ["AI-CONTEXT.md", "AGENT-HANDOFF.md"],
            )

    def test_unstaged_session_files_returns_empty_on_git_error(self):
        with mock.patch.object(
            self.hook.subprocess,
            "check_output",
            side_effect=CalledProcessError(1, "git"),
        ):
            self.assertEqual(self.hook._unstaged_session_files(), [])

    def test_extract_picked_issue_ids_returns_empty_without_picks(self):
        self.assertEqual(self.hook._extract_picked_issue_ids("no picks here"), [])

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

    def test_unstaged_handoff_blocks_commit(self):
        with mock.patch.object(
            self.hook,
            "_unstaged_session_files",
            return_value=["AGENT-HANDOFF.md"],
        ):
            self.assertEqual(self.hook._validate_no_unstaged_session_files(), 1)

    def test_unstaged_ai_context_blocks_commit(self):
        with mock.patch.object(
            self.hook,
            "_unstaged_session_files",
            return_value=["AI-CONTEXT.md"],
        ):
            self.assertEqual(self.hook._validate_no_unstaged_session_files(), 1)

    def test_no_unstaged_session_files_allows_commit_check_to_continue(self):
        with mock.patch.object(
            self.hook,
            "_unstaged_session_files",
            return_value=[],
        ):
            self.assertEqual(self.hook._validate_no_unstaged_session_files(), 0)

    def test_main_rejects_unstaged_session_file_before_other_checks(self):
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=1,
            ),
            mock.patch.object(self.hook, "_commit_touches_handoff") as touches,
        ):
            self.assertEqual(self.hook.main(), 1)
            touches.assert_not_called()

    def test_hook_guidance_does_not_allow_no_verify_bypass(self):
        text = _HOOK_PATH.read_text(encoding="utf-8")
        self.assertNotIn("commit with --no-verify", text)
        self.assertIn("Do not bypass this hook", text)

    def test_rule_docs_name_claude_and_codex_bdd_tdd(self):
        text = (_REPO_ROOT / "AI-CODING-GUIDELINES.md").read_text(encoding="utf-8")
        self.assertIn('"agents" means Claude and Codex', text)
        self.assertIn("BDD means behavior-driven description", text)
        self.assertIn("TDD means test-driven development", text)
        self.assertIn("[BDD PROOF:", text)
        self.assertIn("[TDD PROOF:", text)

    def test_autoissue_test_split_preserves_database_contract_tests(self):
        text = (_REPO_ROOT / "AI-CODING-GUIDELINES.md").read_text(encoding="utf-8")
        self.assertIn("Pure math, parsing, scoring, and fingerprint tests", text)
        self.assertIn("must stay database-backed", text)
        self.assertIn("Claude/Codex learning", text)

    def test_previous_handoff_stamp_reads_second_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake-handoff.md"
            path.write_text(
                "# 2026-05-13 06:15 - Codex\n"
                "body\n"
                "# 2026-05-13 05:45 - Codex\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self.hook._previous_handoff_stamp(path),
                "2026-05-13 05:45",
            )

    def test_previous_handoff_stamp_returns_none_on_read_error(self):
        self.assertIsNone(self.hook._previous_handoff_stamp(Path("missing.md")))

    def test_previous_handoff_stamp_returns_none_with_one_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake-handoff.md"
            path.write_text("# 2026-05-13 06:15 - Codex\nbody\n", encoding="utf-8")
            self.assertIsNone(self.hook._previous_handoff_stamp(path))

    def test_verify_autoissue_quota_rejects_missing_ids(self):
        with mock.patch.object(self.hook, "_read_gate_state", return_value=None):
            self.assertEqual(self.hook._verify_autoissue_quota("no picked ids"), 1)

    def test_verify_autoissue_quota_skips_when_registry_is_empty(self):
        added = _zero_open_ten_source_marker()
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=None),
            mock.patch.object(self.hook.subprocess, "run") as run,
        ):
            self.assertEqual(self.hook._verify_autoissue_quota(added), 0)
        run.assert_not_called()

    def test_verify_autoissue_quota_runs_backend_check(self):
        added = _valid_numeric_ten_source_marker()
        with (
            mock.patch.object(
                self.hook,
                "_previous_handoff_stamp",
                return_value="2026-05-13 05:45",
            ),
            mock.patch.object(
                self.hook.subprocess,
                "run",
                return_value=CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="ok",
                    stderr="",
                ),
            ) as run,
        ):
            self.assertEqual(self.hook._verify_autoissue_quota(added), 0)
        args = run.call_args.args[0]
        self.assertIn("verify_autoissue_quota", args)
        self.assertIn("--resolved-after", args)

    def test_verify_autoissue_quota_rejects_backend_failure(self):
        added = _valid_numeric_ten_source_marker()
        with mock.patch.object(
            self.hook.subprocess,
            "run",
            return_value=CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="bad",
            ),
        ):
            self.assertEqual(self.hook._verify_autoissue_quota(added), 1)

    def test_verify_autoissue_quota_rejects_missing_docker(self):
        added = _valid_numeric_ten_source_marker()
        with mock.patch.object(
            self.hook.subprocess,
            "run",
            side_effect=FileNotFoundError,
        ):
            self.assertEqual(self.hook._verify_autoissue_quota(added), 1)

    def test_verify_autoissue_quota_rejects_system_error(self):
        added = _valid_numeric_ten_source_marker()
        with mock.patch.object(
            self.hook.subprocess,
            "run",
            side_effect=OSError("nope"),
        ):
            self.assertEqual(self.hook._verify_autoissue_quota(added), 1)

    def test_quality_gate_long_file_list_mentions_extra_count(self):
        staged = [f"backend/apps/core/file_{i}.py" for i in range(10)]
        added = _quality_result_marker()
        self.assertEqual(self.hook._validate_quality_gate_for_code(added, staged), 1)

    def test_main_rejects_code_without_staged_handoff(self):
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_generated_build_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_temporary_test_artifacts",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_staged_code_files",
                return_value=[".githooks/check-registry-read.py"],
            ),
            mock.patch.object(
                self.hook,
                "_staged_files",
                return_value=[".githooks/check-registry-read.py"],
            ),
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=False),
        ):
            self.assertEqual(self.hook.main(), 1)

    def test_main_rejects_any_staged_file_without_handoff(self):
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_generated_build_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_temporary_test_artifacts",
                return_value=0,
            ),
            mock.patch.object(self.hook, "_staged_files", return_value=["docs/specs/x.md"]),
            mock.patch.object(self.hook, "_staged_code_files", return_value=[]),
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=False),
            mock.patch.object(sys, "stderr", StringIO()) as err,
        ):
            self.assertEqual(self.hook.main(), 1)
        self.assertIn("30 picked AutoIssue", err.getvalue())

    def test_main_skips_when_handoff_unchanged(self):
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_generated_build_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_temporary_test_artifacts",
                return_value=0,
            ),
            mock.patch.object(self.hook, "_staged_files", return_value=[]),
            mock.patch.object(self.hook, "_staged_code_files", return_value=[]),
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=False),
        ):
            self.assertEqual(self.hook.main(), 0)

    def test_main_stops_after_marker_failure(self):
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_generated_build_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_temporary_test_artifacts",
                return_value=0,
            ),
            mock.patch.object(self.hook, "_staged_code_files", return_value=[]),
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=True),
            mock.patch.object(self.hook, "_staged_diff_for", return_value=""),
        ):
            self.assertEqual(self.hook.main(), 1)

    def test_main_accepts_complete_handoff_markers(self):
        added = (
            _valid_ten_source_marker()
            + "\n[CI FAILED RUNS READ: skipped - gh unavailable]"
            + "\n[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]"
            + "\n"
            + _quality_read_marker()
            + "\n"
            + _quality_result_marker()
            + "\n"
            + _self_review_marker()
            + "\n"
            + _bdd_marker()
            + "\n"
            + _tdd_marker()
            + "\n"
            + _lesson_read_marker()
            + "\n[COVERAGE GAPS READ: 10 picked - #1, #2, #3]"
            + "\n[COVERAGE SUMMARY: target=90% actual=91% - met]"
        )
        with (
            mock.patch.object(
                self.hook,
                "_validate_no_unstaged_session_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_generated_build_files",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_validate_no_temporary_test_artifacts",
                return_value=0,
            ),
            mock.patch.object(
                self.hook,
                "_staged_code_files",
                return_value=[".githooks/check-registry-read.py"],
            ),
            mock.patch.object(self.hook, "_commit_touches_handoff", return_value=True),
            mock.patch.object(self.hook, "_staged_diff_for", return_value=added),
            mock.patch.object(self.hook, "_verify_autoissue_quota", return_value=0),
        ):
            self.assertEqual(self.hook.main(), 0)


class GateTokenValidationTests(unittest.TestCase):
    """Tests for _validate_session_gate_token, _verify_gate_token, _read_gate_state.

    Given the session gate runs at session start and writes session_gate_state.json,
    When the pre-commit hook validates the token,
    Then valid tokens pass, absent/stale/wrong tokens are rejected correctly.
    """

    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def _make_valid_state(self, secret: str, session_type: str, ts_mins: int, total_open: int) -> dict:
        import hashlib, hmac as _hmac_mod
        msg = f"{session_type}|{ts_mins}|{total_open}"
        mac = _hmac_mod.new(secret.encode(), msg.encode(), hashlib.sha256)
        token = mac.hexdigest()[:16]
        return {
            "session_type": session_type,
            "layer2_autoissues": 10,
            "layer2_paper_trail": 3,
            "token": token,
            "ts": ts_mins,
            "total_open_count": total_open,
            "generated_at": "2026-05-28T12:00:00Z",
        }

    def test_absent_state_file_passes(self):
        """Backward-compat: no state file → gate token check passes (returns 0)."""
        with mock.patch.object(self.hook, "_read_gate_state", return_value=None):
            self.assertEqual(self.hook._validate_session_gate_token(), 0)

    def test_valid_token_passes(self):
        """A freshly generated valid token clears the gate check."""
        import time
        secret = "test-secret-hex"
        ts_mins = int(time.time()) // 60
        state = self._make_valid_state(secret, "reconciliation", ts_mins, 42)
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=state),
            mock.patch.dict("os.environ", {"SESSION_GATE_SECRET": secret}),
        ):
            self.assertEqual(self.hook._validate_session_gate_token(), 0)

    def test_wrong_token_fails(self):
        """A token that doesn't match the HMAC is rejected."""
        import time
        secret = "test-secret-hex"
        ts_mins = int(time.time()) // 60
        state = self._make_valid_state(secret, "reconciliation", ts_mins, 42)
        state["token"] = "badc0ffee0badc0f"  # tampered token (wrong hex)
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=state),
            mock.patch.dict("os.environ", {"SESSION_GATE_SECRET": secret}),
            mock.patch.object(sys, "stderr", StringIO()) as err,
        ):
            result = self.hook._validate_session_gate_token()
        self.assertEqual(result, 1)
        self.assertIn("token is invalid or stale", err.getvalue())

    def test_stale_token_fails(self):
        """A token from more than 360 minutes ago is treated as stale."""
        secret = "test-secret-hex"
        old_ts_mins = (1000000)  # far in the past
        state = self._make_valid_state(secret, "feature", old_ts_mins, 10)
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=state),
            mock.patch.dict("os.environ", {"SESSION_GATE_SECRET": secret}),
            mock.patch.object(sys, "stderr", StringIO()),
        ):
            result = self.hook._validate_session_gate_token()
        self.assertEqual(result, 1)

    def test_verify_autoissue_quota_uses_hard_mode_when_gate_state_valid(self):
        """When gate state is valid, _verify_autoissue_quota calls --hard --session-type."""
        import time
        from subprocess import CompletedProcess
        secret = "test-secret-hex"
        ts_mins = int(time.time()) // 60
        state = self._make_valid_state(secret, "reconciliation", ts_mins, 42)
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=state),
            mock.patch.dict("os.environ", {"SESSION_GATE_SECRET": secret}),
            mock.patch.object(
                self.hook.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
            ) as run,
        ):
            result = self.hook._verify_autoissue_quota("marker text with picks")
        self.assertEqual(result, 0)
        args = run.call_args.args[0]
        self.assertIn("--hard", args)
        self.assertIn("--session-type", args)
        self.assertIn("reconciliation", args)
        self.assertNotIn("--ids", args)

    def test_verify_autoissue_quota_uses_ids_when_no_gate_state(self):
        """When gate state is absent, _verify_autoissue_quota falls back to --ids."""
        from subprocess import CompletedProcess
        added = _valid_numeric_ten_source_marker()
        with (
            mock.patch.object(self.hook, "_read_gate_state", return_value=None),
            mock.patch.object(self.hook, "_previous_handoff_stamp", return_value=None),
            mock.patch.object(
                self.hook.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
            ) as run,
        ):
            result = self.hook._verify_autoissue_quota(added)
        self.assertEqual(result, 0)
        args = run.call_args.args[0]
        self.assertIn("--ids", args)
        self.assertNotIn("--hard", args)


if __name__ == "__main__":
    unittest.main()
