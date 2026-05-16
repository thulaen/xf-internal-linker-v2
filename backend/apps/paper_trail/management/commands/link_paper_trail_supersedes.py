"""manage.py link_paper_trail_supersedes — mark old entries as replaced.

Use this when a newer paper-trail entry takes over the work of one or
more older entries. The old entries get `status=superseded` and a FK
pointing to the new entry, so any future search surfaces the chain.

For one-shot supersede during creation, pass --supersedes to
`manage.py defer_work` instead. This command is for after-the-fact
linking.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


class Command(BaseCommand):
    help = "Link one or more old paper-trail entries as superseded by a new one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--new-id",
            type=int,
            required=True,
            help="ID of the newer entry that takes over.",
        )
        parser.add_argument(
            "--old-id",
            type=int,
            action="append",
            required=True,
            help="ID(s) of the older entry that this replaces. Repeat for multiple.",
        )
        parser.add_argument("--agent", default="claude")

    def handle(self, *args, **opts):
        try:
            new_entry = PaperTrailEntry.objects.get(pk=opts["new_id"])
        except PaperTrailEntry.DoesNotExist as exc:
            raise CommandError(
                f"FAIL link_paper_trail_supersedes: --new-id "
                f"#{opts['new_id']} not found.\n"
                "WHY: The newer entry must exist before older ones can "
                "be linked to it.\n"
                "UNBLOCK: File the new entry first via "
                "`manage.py defer_work`, then re-run with its printed id."
            ) from exc

        old_ids: list[int] = opts.get("old_id") or []
        if not old_ids:
            raise CommandError(
                "FAIL link_paper_trail_supersedes: --old-id is required.\n"
                "WHY: Without at least one old entry, there is nothing "
                "to mark as superseded.\n"
                "UNBLOCK: Re-run with --old-id <N> (repeatable)."
            )
        if opts["new_id"] in old_ids:
            raise CommandError(
                "FAIL link_paper_trail_supersedes: --new-id appears in "
                "--old-id list (an entry cannot supersede itself).\n"
                "WHY: A supersede cycle would break the audit chain.\n"
                "UNBLOCK: Re-run with distinct --new-id and --old-id "
                "values."
            )

        linked: list[int] = []
        already: list[int] = []
        missing: list[int] = []
        for old_id in old_ids:
            try:
                old = PaperTrailEntry.objects.get(pk=old_id)
            except PaperTrailEntry.DoesNotExist:
                missing.append(old_id)
                continue
            if old.status == PaperTrailEntry.STATUS_SUPERSEDED:
                already.append(old.pk)
                continue
            old.superseded_by = new_entry
            old.status = PaperTrailEntry.STATUS_SUPERSEDED
            old.suppression_approver = (opts.get("agent") or "")[:64]
            old.last_seen = timezone.now()
            old.save()
            linked.append(old.pk)

        if missing:
            self.stdout.write(
                f"[PAPER TRAIL SUPERSEDE WARN: ids not found: "
                f"{', '.join(f'#{i}' for i in missing)}]"
            )
        if already:
            self.stdout.write(
                f"[PAPER TRAIL SUPERSEDE NO-OP: already superseded: "
                f"{', '.join(f'#{i}' for i in already)}]"
            )
        if linked:
            self.stdout.write(
                f"[PAPER TRAIL SUPERSEDED: #{new_entry.pk} now replaces "
                f"{', '.join(f'#{i}' for i in linked)}]"
            )
