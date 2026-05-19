"""Tests for manage.py preflight_tdd — Session S1 of the TDD-pipeline rule.

Written FIRST (Red) per the strict-TDD rule the command itself helps enforce.
The command MUST:

  * Print a `[TDD PREFLIGHT: ...]` marker to stdout.
  * Include the pipeline shape (`SPEC → TEST_CASE → TDD → CODE → CODE_REVIEW → LESSON`).
  * Include `armed_at=<ISO8601>` and `session_id=<value>` slots.
  * Include the eight pipeline switches all set to `on`.
  * Honour `--session-id` to make the marker reproducible for tests.
  * Honour `--dry-run` to validate inputs without emitting the real marker.
  * Be a no-op on the DB beyond `get_or_create` on the required category rows.

Spec ref: docs/TDD-PIPELINE-RULE.md (to be authored in Session S4).
"""

from __future__ import annotations

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


_PREFLIGHT_RE = re.compile(
    r"\[TDD PREFLIGHT:\s*"
    r"pipeline=(?P<pipeline>\S+)\s+"
    r"spec_citation=(?P<spec_citation>\S+)\s+"
    r"test_case_mandate=(?P<test_case_mandate>\S+)\s+"
    r"tdd_red_green_refactor=(?P<tdd_red_green_refactor>\S+)\s+"
    r"5_layer_coverage=(?P<five_layer>\S+)\s+"
    r"code_review_logging=(?P<code_review>\S+)\s+"
    r"lesson_logging=(?P<lesson_logging>\S+)\s+"
    r"decision_point=(?P<decision_point>\S+)\s+"
    r"artefact_pruning=(?P<artefact_pruning>\S+)\s+"
    r"no_bypass=(?P<no_bypass>\S+)\s+"
    r"per_file_lookup=(?P<per_file_lookup>\S+)\s+"
    r"commit_failure_lookup=(?P<commit_failure_lookup>\S+)\s+"
    r"session_id=(?P<session_id>\S+)\s+"
    r"armed_at=(?P<armed_at>\S+)\]"
)


def _call(*args: str) -> str:
    out = StringIO()
    call_command("preflight_tdd", *args, stdout=out)
    return out.getvalue()


class PreflightTddMarkerShapeTests(TestCase):
    """The marker shape MUST match the regex the hook will validate."""

    def test_marker_is_emitted(self) -> None:
        output = _call()
        self.assertIn("[TDD PREFLIGHT:", output)

    def test_marker_matches_full_shape(self) -> None:
        output = _call()
        match = _PREFLIGHT_RE.search(output)
        self.assertIsNotNone(
            match,
            msg=f"emitted marker did not match the full shape: {output!r}",
        )

    def test_pipeline_string_carries_code_review_stage(self) -> None:
        output = _call()
        match = _PREFLIGHT_RE.search(output)
        assert match is not None
        pipeline = match.group("pipeline")
        for stage in ("SPEC", "TEST_CASE", "TDD", "CODE", "CODE_REVIEW", "LESSON"):
            self.assertIn(stage, pipeline)
        self.assertLess(pipeline.index("CODE"), pipeline.index("CODE_REVIEW"))
        self.assertLess(pipeline.index("CODE_REVIEW"), pipeline.index("LESSON"))

    def test_preflight_explains_code_review_cannot_be_skipped(self) -> None:
        output = _call()
        self.assertIn("[TDD PREFLIGHT PIPELINE:", output)
        self.assertIn("CODE REVIEW", output)
        self.assertIn("after-the-fact check", output)
        self.assertIn("persisted for the next agent", output)

    def test_every_pipeline_switch_is_on(self) -> None:
        output = _call()
        match = _PREFLIGHT_RE.search(output)
        assert match is not None
        for field in (
            "spec_citation",
            "test_case_mandate",
            "tdd_red_green_refactor",
            "five_layer",
            "code_review",
            "lesson_logging",
            "decision_point",
            "artefact_pruning",
            "no_bypass",
            "per_file_lookup",
            "commit_failure_lookup",
        ):
            self.assertEqual(match.group(field), "on")

    def test_armed_at_is_iso8601_utc(self) -> None:
        output = _call()
        match = _PREFLIGHT_RE.search(output)
        assert match is not None
        armed_at = match.group("armed_at")
        # ISO8601 UTC, ending in Z or +00:00.
        self.assertRegex(armed_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")


class PreflightTddSessionIdTests(TestCase):

    def test_default_session_id_is_uuid_shaped(self) -> None:
        output = _call()
        match = _PREFLIGHT_RE.search(output)
        assert match is not None
        session_id = match.group("session_id")
        # UUID4 string: 8-4-4-4-12 hex digits with dashes.
        self.assertRegex(session_id, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def test_explicit_session_id_is_honoured(self) -> None:
        output = _call("--session-id", "S1-test-session-42")
        match = _PREFLIGHT_RE.search(output)
        assert match is not None
        self.assertEqual(match.group("session_id"), "S1-test-session-42")


class PreflightTddDryRunTests(TestCase):

    def test_dry_run_does_not_emit_real_marker(self) -> None:
        output = _call("--dry-run")
        # Dry-run prints a DRY-RUN marker; real PREFLIGHT marker MUST be absent.
        self.assertNotIn("[TDD PREFLIGHT:", output)
        self.assertIn("DRY-RUN", output)


class PreflightTddCategoryBootstrapTests(TestCase):
    """The command bootstraps the AutoIssueCategory rows the pipeline depends on."""

    _REQUIRED_KEYS = (
        "test_case",
        "tdd_lesson",
        "code_review_lesson",
        "hook_failure",
        "decision_point",
    )

    def test_required_categories_exist_after_preflight(self) -> None:
        _call()
        keys = set(AutoIssueCategory.objects.values_list("key", flat=True))
        for required in self._REQUIRED_KEYS:
            self.assertIn(required, keys, msg=f"missing AutoIssueCategory: {required}")

    def test_preflight_is_idempotent_on_categories(self) -> None:
        _call()
        before = AutoIssueCategory.objects.count()
        _call()
        after = AutoIssueCategory.objects.count()
        self.assertEqual(before, after)


class VerifyTddLessonBatchTests(TestCase):
    """The strict hook can verify all lesson rows in one command call."""

    def _lesson(self, title: str) -> AutoIssue:
        category, _ = AutoIssueCategory.objects.get_or_create(
            key="tdd_lesson",
            defaults={
                "label": "TDD lesson",
                "description": "Resolved strict-TDD lesson rows.",
                "sort_order": 210,
            },
        )
        return AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id=f"batch-tdd-lesson-{title}",
            fingerprint=f"batch-tdd-lesson-{title}",
            canonical_fingerprint=f"batch-tdd-lesson-{title}",
            title=title,
            description="Batch verifier test lesson.",
            affected_files=["backend/apps/foo.py"],
            severity=AutoIssue.SEVERITY_LOW,
            category=category,
            status=AutoIssue.STATUS_RESOLVED,
            lessons_learned="Trap: per-id checks are slow. Fix shape: batch ids.",
        )

    def test_verify_tdd_lesson_accepts_repeated_ids(self) -> None:
        first = self._lesson("first batch lesson")
        second = self._lesson("second batch lesson")
        out = StringIO()

        call_command(
            "verify_tdd_lesson",
            "--id", str(first.pk),
            "--id", str(second.pk),
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn(f"[TDD LESSON VERIFIED: AutoIssue=#{first.pk}]", text)
        self.assertIn(f"[TDD LESSON VERIFIED: AutoIssue=#{second.pk}]", text)
