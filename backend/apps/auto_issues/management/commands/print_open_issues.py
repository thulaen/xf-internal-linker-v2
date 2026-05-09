"""Print the open auto-issues an agent should consider before any new task.

Used by the pre-session hook (``.githooks/print-open-issues.ps1``) and by
the ``[REGISTRY READ: ...]`` startup marker every agent must emit per the
ABSOLUTE rule in CLAUDE.md. Output is intentionally compact so it fits
in a session-start banner.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Print open AutoIssue rows in priority order. Used at session start."

    _DEFAULT_LIMIT = 10
    _OPEN_STATUSES = (AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=self._DEFAULT_LIMIT,
            help=f"Max rows to print (default {self._DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--source",
            choices=[c[0] for c in AutoIssue.SOURCE_CHOICES],
            default=None,
            help="Restrict to one source (glitchtip, pyroscope, agent).",
        )

    def handle(self, *args, **opts):
        qs = AutoIssue.objects.filter(status__in=self._OPEN_STATUSES)
        if opts["source"]:
            qs = qs.filter(source=opts["source"])
        qs = qs.order_by("-priority_score", "-last_seen")[: opts["limit"]]

        rows = list(qs)
        if not rows:
            self.stdout.write("[REGISTRY READ: 0 open auto-issues]")
            return

        self.stdout.write(
            f"[REGISTRY READ: {AutoIssue.objects.filter(status__in=self._OPEN_STATUSES).count()} open, "
            f"showing top {len(rows)}]"
        )
        for r in rows:
            files = ",".join(r.affected_files[:3]) if r.affected_files else ""
            file_hint = f" — {files}" if files else ""
            self.stdout.write(
                f"  #{r.id} [{r.source}/{r.severity}] {r.title[:80]}{file_hint}"
            )
