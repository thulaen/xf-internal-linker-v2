"""manage.py mark_paper_trail_stale — flag an entry as no-longer-relevant.

Use this when the code, system, or decision the entry was tracking has
moved on enough that the entry no longer reflects reality (but the entry
hasn't been formally rejected and isn't a duplicate either).

The agent MUST supply --reason explaining why the entry is stale. The
reason is stored in `suppression_reason` and surfaces in the history
audit log so future searches can see who marked it stale and why.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


class Command(BaseCommand):
    help = "Mark a paper-trail entry as stale with a plain-English reason."

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True)
        parser.add_argument(
            "--reason",
            required=True,
            help="Plain-English reason this entry is no longer relevant.",
        )
        parser.add_argument("--agent", default="claude")

    def handle(self, *args, **opts):
        reason = (opts["reason"] or "").strip()
        if not reason:
            raise CommandError(
                "FAIL mark_paper_trail_stale: --reason is required.\n"
                "WHY: A stale entry without a reason loses the audit "
                "trail — the next agent can't tell whether the staleness "
                "is correct or a mistake.\n"
                "UNBLOCK: Re-run with --reason \"<plain-English explanation>\"."
            )
        try:
            entry = PaperTrailEntry.objects.get(pk=opts["id"])
        except PaperTrailEntry.DoesNotExist as exc:
            raise CommandError(
                f"FAIL mark_paper_trail_stale: paper-trail entry "
                f"#{opts['id']} not found.\n"
                "WHY: The id supplied does not exist in the database.\n"
                "UNBLOCK: Run `manage.py search_paper_trail --keyword ...` "
                "to find the right id, then re-run."
            ) from exc
        if entry.status == PaperTrailEntry.STATUS_STALE:
            self.stdout.write(
                f"[PAPER TRAIL STALE NO-OP: #{entry.pk} already stale]"
            )
            return
        entry.status = PaperTrailEntry.STATUS_STALE
        entry.suppression_reason = reason[:2000]
        entry.suppression_approver = (opts.get("agent") or "")[:64]
        entry.last_seen = timezone.now()
        entry.save()
        self.stdout.write(f"[PAPER TRAIL STALE: #{entry.pk}]")
