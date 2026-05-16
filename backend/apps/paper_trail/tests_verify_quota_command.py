"""TDD tests for verify_paper_trail_quota command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


def _resolved(title: str, *, resolved_at, lessons="Trap: x. Fix shape: y.") -> PaperTrailEntry:
    entry = PaperTrailEntry.objects.create(
        category=PaperTrailEntry.CATEGORY_OTHER,
        title=title,
        abstract=(
            "Given the verify_quota tests need a paper-trail row, "
            "When _resolved() constructs one, "
            "Then it passes BDD validation."
        ),
        deferred_by="test",
        risk_on_inaction="Test only.",
        acceptance_criteria="Test passes.",
    )
    entry.status = PaperTrailEntry.STATUS_RESOLVED
    entry.resolved_at = resolved_at
    entry.resolved_by = "claude"
    entry.resolution_lessons = lessons
    entry.save()
    return entry


class VerifyQuotaTests(TestCase):
    """Quota was lowered 10→3 and broadened to every commit on 2026-05-16."""

    def test_passes_with_3_resolved(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(3)]
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--ids", *[str(i) for i in ids],
            stdout=out,
        )
        self.assertIn("QUOTA VERIFIED", out.getvalue())
        self.assertIn("3 resolved", out.getvalue())

    def test_fails_with_2(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(2)]
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_fails_on_duplicate_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(2)]
        ids.append(ids[0])  # 3 IDs but one duplicate
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_fails_when_resolved_before_cutoff(self) -> None:
        old = timezone.now() - timedelta(days=3)
        ids = [_resolved(f"t{i}", resolved_at=old).pk for i in range(3)]
        cutoff = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                "--resolved-after", cutoff,
                stdout=StringIO(),
            )

    def test_fails_on_missing_lesson_tokens(self) -> None:
        """Model save() rejects malformed lessons, but the verify gate is
        the FINAL check before commit. The gate must independently catch
        rows that bypassed validation (raw SQL, fixture load, etc.).
        Use queryset.update() to bypass save() so we can test the gate.
        """
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(3)]
        # Bypass save() to simulate a malformed row.
        PaperTrailEntry.objects.filter(pk__in=ids).update(
            resolution_lessons="Trap: only — no fix-shape part"
        )
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                stdout=StringIO(),
            )
