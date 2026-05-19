"""Shared helpers for paper-trail tests."""

from __future__ import annotations

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.paper_trail.models import PaperTrailEntry


FULL_TEST_CASE_LESSON = (
    "Given a paper-trail test fixture needs a complete contract\n"
    "When the test creates a PaperTrailEntry row\n"
    "Then the evidence rule accepts the row\n"
    "Edge cases: missing citation and missing test-case link fail\n"
    "Failure cases: malformed BDD text is rejected\n"
    "Security: fixture citations use public stable identifiers\n"
    "Usability: helpers keep tests short and readable\n"
    "Scalability: one linked AutoIssue keeps validation bounded\n"
    "Maintainability: shared helper prevents stale fixtures\n"
    "Regression risks: evidence requirements must stay visible in tests"
)


def make_test_case(*, affected_files: list[str] | None = None) -> AutoIssue:
    category, _created = AutoIssueCategory.objects.get_or_create(
        key="test_case",
        defaults={
            "label": "Test case spec",
            "description": "Test-only full BDD contract.",
            "sort_order": 215,
        },
    )
    index = AutoIssue.objects.count() + 1
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"paper-trail-test-case-{index}",
        fingerprint=f"paper-trail-test-case-{index}",
        canonical_fingerprint=f"paper-trail-test-case-{index}",
        title=f"Paper trail test case {index}",
        description="Test-only paper-trail evidence contract.",
        affected_files=affected_files or ["backend/apps/paper_trail"],
        severity=AutoIssue.SEVERITY_LOW,
        category=category,
        status=AutoIssue.STATUS_OPEN,
        lessons_learned=FULL_TEST_CASE_LESSON,
    )


def valid_paper_trail_defaults(**overrides) -> dict:
    test_case = make_test_case(affected_files=overrides.get("affected_files"))
    defaults = {
        "category": PaperTrailEntry.CATEGORY_OTHER,
        "title": "valid paper-trail test row",
        "abstract": (
            "Given a paper-trail test needs a valid row, "
            "When valid_paper_trail_defaults builds the fields, "
            "Then the row passes today's evidence validation."
        ),
        "deferred_by": "test",
        "risk_on_inaction": "Test-only entry; no real user risk.",
        "acceptance_criteria": "The test passes when the row saves.",
        "test_case_autoissue_id": test_case.pk,
        "citations": ["RFC 9110"],
    }
    defaults.update(overrides)
    return defaults
