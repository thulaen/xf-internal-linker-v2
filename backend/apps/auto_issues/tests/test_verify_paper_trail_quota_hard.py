"""BDD-shaped tests for hard paper-trail quota verification."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.tests_helpers import valid_paper_trail_defaults


class VerifyPaperTrailQuotaHardTests(TestCase):
    def test_paper_trail_quota_met_exits_zero(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_resolved_entries(10)

        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            hard=True,
            resolved_after=_stamp(cutoff),
            stdout=out,
        )

        self.assertIn("[PAPER TRAIL QUOTA VERIFIED: 10 resolved]", out.getvalue())

    def test_paper_trail_count_short_refuses(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_resolved_entries(6)

        with self.assertRaisesMessage(
            CommandError, "paper-trail: 6 of 10 resolved (4 short)"
        ):
            call_command(
                "verify_paper_trail_quota",
                hard=True,
                resolved_after=_stamp(cutoff),
            )


def _create_resolved_entries(count: int) -> None:
    now = timezone.now()
    for index in range(count):
        entry = PaperTrailEntry.objects.create(
            **valid_paper_trail_defaults(
                category=PaperTrailEntry.CATEGORY_OTHER,
                title=f"Hard quota paper trail {index}",
                abstract=(
                    "Given hard quota tests need resolved entries, "
                    "When the verifier counts them, "
                    "Then the paper-trail total is enforced."
                ),
            )
        )
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = now
        entry.resolved_by = "codex-test"
        entry.resolution_lessons = (
            "Trap: hard quota rows need two-part resolution lessons. "
            "Fix shape: create resolved paper-trail rows with lessons."
        )
        entry.save()


def _stamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M")
