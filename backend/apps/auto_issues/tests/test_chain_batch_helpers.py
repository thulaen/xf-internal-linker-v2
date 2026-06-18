"""Convention SimpleTestCase guards for chain_batch pure helpers.

No database: every helper here turns plain dict "rows" (the shape returned by
``QuerySet.values()``) or a list of ids into a pass/fail Result or an error
    list. The EXACT assertions below kill mutation survivors on the boundary
    numbers (28, 10), the status comparisons, the keyword membership checks, and
the cutoff datetime comparison.
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_tz

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.chain_batch import (
    _duplicate_canonical_errors,
    _is_resolved_code_review,
    _missing_errors,
    _paper_evidence_core_errors,
    _quota_count_errors,
    _referenced_issue_ids,
    _render_ids,
    _requires_resolution_evidence,
    _resolved_time_errors,
    _test_case_result,
    _unique_ids,
    _RESOLUTION_EVIDENCE_CUTOFF,
    _line_failed_within_hour,
)


class TestCaseResultTests(SimpleTestCase):
    def test_all_three_keywords_present_passes(self):
        self.assertEqual(
            _test_case_result("Given a thing When acted Then result"),
            {"status": "pass"},
        )

    def test_keyword_match_is_case_insensitive(self):
        self.assertEqual(
            _test_case_result("given x when y then z"),
            {"status": "pass"},
        )

    def test_missing_keyword_lists_it_exactly(self):
        result = _test_case_result("Given x When y")
        self.assertEqual(result, {"status": "fail", "reason": "missing Then"})


class QuotaCountErrorsTests(SimpleTestCase):
    def test_exact_count_no_errors(self):
        self.assertEqual(_quota_count_errors([1, 2, 3], 3, "AutoIssue"), [])

    def test_wrong_count_reports_expected_and_got(self):
        self.assertEqual(
            _quota_count_errors([1, 2], 3, "AutoIssue"),
            ["expected 3 AutoIssue ids, got 2"],
        )

    def test_duplicate_ids_flagged(self):
        errors = _quota_count_errors([1, 1, 2], 3, "AutoIssue")
        self.assertIn("duplicate AutoIssue ids are not allowed", errors)





class MissingAndDuplicateTests(SimpleTestCase):
    def test_missing_errors_lists_absent_ids(self):
        self.assertEqual(
            _missing_errors([1, 2, 3], {1: {}, 3: {}}, "AutoIssue"),
            ["missing AutoIssue ids: #2"],
        )

    def test_missing_errors_empty_when_all_present(self):
        self.assertEqual(_missing_errors([1], {1: {}}, "AutoIssue"), [])

    def test_duplicate_canonical_groups_by_fingerprint(self):
        rows = {
            1: {"canonical_fingerprint": "abc"},
            2: {"canonical_fingerprint": "abc"},
            3: {"canonical_fingerprint": "xyz"},
        }
        errors = _duplicate_canonical_errors([1, 2, 3], rows, "AutoIssue")
        self.assertEqual(errors, ["duplicate AutoIssue work: #1, #2"])

    def test_no_duplicate_canonical_when_unique(self):
        rows = {1: {"canonical_fingerprint": "a"}, 2: {"canonical_fingerprint": "b"}}
        self.assertEqual(_duplicate_canonical_errors([1, 2], rows, "AutoIssue"), [])


class ResolvedTimeErrorsTests(SimpleTestCase):
    def test_none_resolved_at_flags_missing_time(self):
        self.assertEqual(
            _resolved_time_errors(5, None, None),
            ["#5 has no resolved_at time"],
        )

    def test_resolved_at_at_or_before_cutoff_flagged(self):
        cutoff = datetime(2026, 5, 1, tzinfo=dt_tz.utc)
        at_cutoff = datetime(2026, 5, 1, tzinfo=dt_tz.utc)
        self.assertEqual(
            _resolved_time_errors(5, at_cutoff, cutoff),
            ["#5 was resolved before the cutoff"],
        )

    def test_resolved_after_cutoff_passes(self):
        cutoff = datetime(2026, 5, 1, tzinfo=dt_tz.utc)
        later = datetime(2026, 5, 2, tzinfo=dt_tz.utc)
        self.assertEqual(_resolved_time_errors(5, later, cutoff), [])


class ReferencedIssueIdsTests(SimpleTestCase):
    def test_extracts_unique_ids_in_first_seen_order(self):
        self.assertEqual(_referenced_issue_ids("see #12 and #7 and #12"), [12, 7])

    def test_empty_text_yields_empty_list(self):
        self.assertEqual(_referenced_issue_ids(""), [])


class RequiresResolutionEvidenceTests(SimpleTestCase):
    def test_non_resolved_status_does_not_require_evidence(self):
        self.assertFalse(_requires_resolution_evidence({"status": "open"}))

    def test_resolved_with_no_time_requires_evidence(self):
        self.assertTrue(
            _requires_resolution_evidence({"status": "resolved", "resolved_at": None})
        )

    def test_resolved_at_cutoff_boundary_requires_evidence(self):
        self.assertTrue(
            _requires_resolution_evidence(
                {"status": "resolved", "resolved_at": _RESOLUTION_EVIDENCE_CUTOFF}
            )
        )

    def test_resolved_before_cutoff_skips_evidence(self):
        before = datetime(2026, 5, 23, 17, 59, 59, tzinfo=dt_tz.utc)
        self.assertFalse(
            _requires_resolution_evidence(
                {"status": "resolved", "resolved_at": before}
            )
        )


class IsResolvedCodeReviewTests(SimpleTestCase):
    def test_resolved_code_review_lesson_true(self):
        self.assertTrue(
            _is_resolved_code_review(
                {"category__key": "code_review_lesson", "status": "resolved"}
            )
        )

    def test_wrong_category_false(self):
        self.assertFalse(
            _is_resolved_code_review(
                {"category__key": "tdd_lesson", "status": "resolved"}
            )
        )

    def test_none_row_false(self):
        self.assertFalse(_is_resolved_code_review(None))


class PaperEvidenceCoreErrorsTests(SimpleTestCase):
    def test_all_fields_and_bdd_keywords_present(self):
        row = {
            "abstract": "Given a When b Then c",
            "risk_on_inaction": "risk",
            "acceptance_criteria": "criteria",
        }
        self.assertEqual(_paper_evidence_core_errors(row), [])

    def test_missing_field_and_keyword_reported(self):
        row = {"abstract": "Given a When b", "risk_on_inaction": "", "acceptance_criteria": "c"}
        errors = _paper_evidence_core_errors(row)
        self.assertIn("missing risk_on_inaction", errors)
        self.assertIn("abstract missing Then", errors)


class LineFailedWithinHourTests(SimpleTestCase):
    def test_failure_at_or_after_cutoff_counts_one(self):
        cutoff = datetime(2026, 6, 3, 12, 0, 0, tzinfo=dt_tz.utc)
        line = '{"failed_at": "2026-06-03T12:30:00Z"}'
        self.assertEqual(_line_failed_within_hour(line, cutoff), 1)

    def test_failure_before_cutoff_counts_zero(self):
        cutoff = datetime(2026, 6, 3, 12, 0, 0, tzinfo=dt_tz.utc)
        line = '{"failed_at": "2026-06-03T11:00:00Z"}'
        self.assertEqual(_line_failed_within_hour(line, cutoff), 0)

    def test_unparseable_line_counts_zero(self):
        cutoff = datetime(2026, 6, 3, 12, 0, 0, tzinfo=dt_tz.utc)
        self.assertEqual(_line_failed_within_hour("not json", cutoff), 0)

    def test_missing_failed_at_counts_zero(self):
        cutoff = datetime(2026, 6, 3, 12, 0, 0, tzinfo=dt_tz.utc)
        self.assertEqual(_line_failed_within_hour('{"other": 1}', cutoff), 0)


class SmallHelperTests(SimpleTestCase):
    def test_unique_ids_preserves_order_and_drops_repeats(self):
        self.assertEqual(_unique_ids([3, 1, 3, 2, 1]), [3, 1, 2])

    def test_render_ids_prefixes_hash(self):
        self.assertEqual(_render_ids([1, 2]), "#1, #2")
