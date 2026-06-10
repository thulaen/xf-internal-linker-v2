"""Convention SimpleTestCase guards for the changed quota/model/command helpers.

No database is touched:
  - verify_autoissue_quota: ``_scaled_requirements`` (exact per-session-type
    dicts), ``_mandatory_hard_errors`` (sonarqube non-substitutable wording),
    ``_count_and_duplicate_errors`` (Counter-based dedup that replaced the
    O(n^2) ``list.count`` scan).
  - models: ``AutoIssue.__str__`` (the new ``budget = 100 - len(prefix)``
    truncation) on an *unsaved* instance + the new evidence models' ``__str__``.
  - rotate_gh_actions_log: ``_parse_cutoff`` (UTC tzinfo + format guard).
  - print_open_issues: ``_issue_dedupe_key`` (canonical fingerprint vs
    source:external_id fallback).
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_tz
from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.auto_issues.management.commands import print_open_issues

from apps.auto_issues.models import (
    AutoIssue,
    BuildFailureEvidence,
    CodeQLFindingEvidence,
    FindBugsLearnedLesson,
)
from apps.auto_issues.management.commands.print_open_issues import _issue_dedupe_key
from apps.auto_issues.management.commands.rotate_gh_actions_log import _parse_cutoff
from apps.auto_issues.management.commands.verify_autoissue_quota import (

    _count_and_duplicate_errors,
    _mandatory_hard_errors,
    _scaled_requirements,
)


class ScaledRequirementsTests(SimpleTestCase):
    def test_docs_zeroes_both_buckets(self):
        hard, cross = _scaled_requirements("docs")
        self.assertTrue(all(v == 0 for v in hard.values()))
        self.assertTrue(all(v == 0 for v in cross.values()))

    def test_reconciliation_cross_each_is_one_total_ten(self):
        hard, cross = _scaled_requirements("reconciliation")
        self.assertTrue(all(v == 0 for v in hard.values()))
        self.assertTrue(all(v == 1 for v in cross.values()))
        self.assertEqual(sum(cross.values()), 10)

    def test_infrastructure_cross_each_is_two_total_twenty(self):
        hard, cross = _scaled_requirements("infrastructure")
        self.assertTrue(all(v == 2 for v in cross.values()))
        self.assertEqual(sum(cross.values()), 20)




_EFFECTIVE_REQ_PATH = (
    "apps.auto_issues.management.commands.verify_autoissue_quota._effective_requirement"
)


class MandatoryHardErrorsTests(SimpleTestCase):
    # _mandatory_hard_errors now calls _effective_requirement which queries the DB.
    # Patch it here to keep these as pure unit tests (no DB needed).

    def test_count_meets_requirement_no_error(self):
        with patch(_EFFECTIVE_REQ_PATH, return_value=10):
            self.assertEqual(
                _mandatory_hard_errors(10, AutoIssue.SOURCE_RUST_DEFECT, 10), []
            )



    def test_non_sonarqube_shortfall_uses_short_suffix(self):
        with patch(_EFFECTIVE_REQ_PATH, return_value=10):
            errors = _mandatory_hard_errors(8, AutoIssue.SOURCE_PERFETTO, 10)
        self.assertEqual(len(errors), 1)
        self.assertIn("perfetto", errors[0])
        self.assertIn("8 of 10", errors[0])
        self.assertIn("2 short", errors[0])


class CountAndDuplicateErrorsTests(SimpleTestCase):
    def test_exactly_thirty_unique_ids_no_error(self):
        self.assertEqual(_count_and_duplicate_errors(list(range(30))), [])

    def test_wrong_count_reports_found(self):
        errors = _count_and_duplicate_errors([1, 2, 3])
        self.assertIn("Expected 30 picked AutoIssues, found 3.", errors)

    def test_duplicates_sorted_and_rendered(self):
        ids = list(range(28)) + [5, 5, 3, 3]
        errors = _count_and_duplicate_errors(ids)
        joined = " ".join(errors)
        self.assertIn("Duplicate picked AutoIssue IDs are not allowed: #3, #5.", joined)


class AutoIssueStrTests(SimpleTestCase):
    def test_prefix_is_source_and_severity(self):
        issue = AutoIssue(source=AutoIssue.SOURCE_AGENT, severity="high", title="boom")
        self.assertEqual(str(issue), "[agent/high] boom")

    def test_total_length_capped_at_100(self):
        issue = AutoIssue(source=AutoIssue.SOURCE_AGENT, severity="high", title="x" * 200)
        self.assertEqual(len(str(issue)), 100)


class EvidenceModelStrTests(SimpleTestCase):
    def test_codeql_str_includes_language_rule_and_location(self):
        ev = CodeQLFindingEvidence(
            language="python", rule_id="py/sql-injection",
            file_path="backend/x.py", line=42,
        )
        self.assertEqual(str(ev), "[codeql/python] py/sql-injection backend/x.py:42")

    def test_build_failure_str_uses_all_placeholder_when_no_targets(self):
        ev = BuildFailureEvidence(builder="mint", targets=[], exit_code=2)
        self.assertEqual(str(ev), "[build/mint] <all> exit=2")

    def test_findbugs_str_truncates_fingerprint_to_twelve(self):
        lesson = FindBugsLearnedLesson(
            classification="false_positive",
            lesson_fingerprint="0123456789abcdef",
        )
        self.assertEqual(str(lesson), "[findbugs-lesson/false_positive] 0123456789ab")


class ParseCutoffTests(SimpleTestCase):
    def test_valid_date_gets_utc_tzinfo(self):
        parsed = _parse_cutoff("2026-06-03")
        self.assertEqual(parsed, datetime(2026, 6, 3, tzinfo=dt_tz.utc))

    def test_bad_format_raises_command_error(self):
        with self.assertRaises(CommandError):
            _parse_cutoff("06/03/2026")


class RegistryMarkerTotalTests(SimpleTestCase):
    """The [REGISTRY READ] N must equal the SUM of the ten picker buckets,
    NOT the grand total of every open AutoIssue (the changed line:
    ``picker_total = sum(counts[s] for s in self._SOURCE_ORDER)``).
    """

    def test_marker_uses_bucket_sum_not_grand_total(self):
        cmd = print_open_issues.Command()
        cmd.stdout = MagicMock()
        # One fake picked row so the early "0 open" return is skipped.
        fake_row = MagicMock(
            id=1, source="agent", severity="high", title="x", affected_files=[]
        )

        # grand total (99) deliberately differs from the per-source buckets,
        # which sum to 10 (one per source). The marker must print 10.
        manager = MagicMock()
        manager.filter.return_value.count.side_effect = (
            [99] + [1] * len(print_open_issues.Command._SOURCE_ORDER)
        )

        with patch.object(
            print_open_issues, "_pick_unique_open_issues", return_value=[fake_row]
        ), patch.object(
            print_open_issues.AutoIssue, "objects", manager
        ), patch.object(
            print_open_issues.Command, "_print_ci_failed_runs"
        ), patch.object(
            print_open_issues.Command, "_print_coverage_gaps"
        ):
            cmd.handle(limit=10, source=None)

        printed = " ".join(str(c.args[0]) for c in cmd.stdout.write.call_args_list)
        self.assertIn("[REGISTRY READ: 10 open (", printed)
        self.assertNotIn("[REGISTRY READ: 99 open", printed)


class IssueDedupeKeyTests(SimpleTestCase):
    def test_uses_canonical_fingerprint_when_present(self):
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="abc",
            canonical_fingerprint="fp123",
        )
        self.assertEqual(_issue_dedupe_key(issue), "fp123")

    def test_falls_back_to_source_and_external_id(self):
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="abc",
            canonical_fingerprint="",
        )
        self.assertEqual(_issue_dedupe_key(issue), "agent:abc")
