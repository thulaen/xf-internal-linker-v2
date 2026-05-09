"""Print recently-resolved AutoIssue rows.

Used at session start as a complement to `print_open_issues`. Surfaces
the most recent fixes so an agent can see: what was just shipped, by
whom, and what the resolving agent learned. Intentionally compact so
it fits in the session-start banner alongside the open-issues list.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Print recently-resolved AutoIssue rows so agents know what was just shipped."

    _DEFAULT_LIMIT = 5
    _DEFAULT_LOOKBACK_DAYS = 14

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=self._DEFAULT_LIMIT,
            help=f"Max rows to print (default {self._DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=self._DEFAULT_LOOKBACK_DAYS,
            help=f"Lookback window in days (default {self._DEFAULT_LOOKBACK_DAYS}).",
        )

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts["days"])
        qs = (
            AutoIssue.objects.filter(
                status=AutoIssue.STATUS_RESOLVED, resolved_at__gte=cutoff
            )
            .order_by("-resolved_at")[: opts["limit"]]
        )
        rows = list(qs)
        total = AutoIssue.objects.filter(
            status=AutoIssue.STATUS_RESOLVED
        ).count()
        if not rows:
            self.stdout.write(
                f"[RESOLVED HISTORY: 0 fixes in last {opts['days']}d ({total} total all-time)]"
            )
            return
        self.stdout.write(
            f"[RESOLVED HISTORY: {len(rows)} recent fix(es), {total} total all-time]"
        )
        for r in rows:
            date = r.resolved_at.strftime("%Y-%m-%d") if r.resolved_at else "????-??-??"
            by = r.resolved_by or "?"
            self.stdout.write(
                f"  #{r.id} ({date} by {by}) [{r.source}/{r.severity}] {r.title[:80]}"
            )
