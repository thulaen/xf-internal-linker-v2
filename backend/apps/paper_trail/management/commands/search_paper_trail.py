"""manage.py search_paper_trail — find entries by area / category / keyword."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.paper_trail.models import PaperTrailEntry


_SEVERITY_RANK = {
    PaperTrailEntry.SEVERITY_LOW: 1,
    PaperTrailEntry.SEVERITY_MEDIUM: 2,
    PaperTrailEntry.SEVERITY_HIGH: 3,
    PaperTrailEntry.SEVERITY_CRITICAL: 4,
}


class Command(BaseCommand):
    help = "Search paper-trail entries by path, category, severity, or keyword."

    def add_arguments(self, parser):
        parser.add_argument("--area", action="append", default=[])
        parser.add_argument("--category", default=None)
        parser.add_argument("--severity", default=None,
                            help="Minimum severity floor (low|medium|high|critical).")
        parser.add_argument("--keyword", default=None)
        parser.add_argument("--include-resolved", action="store_true")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **opts):
        qs = PaperTrailEntry.objects.all()
        if not opts["include_resolved"]:
            qs = qs.filter(status__in=PaperTrailEntry._ACTIVE_STATUSES)
        if opts["category"]:
            qs = qs.filter(category=opts["category"])
        if opts["severity"]:
            floor = _SEVERITY_RANK.get(opts["severity"], 0)
            allowed = [s for s, rank in _SEVERITY_RANK.items() if rank >= floor]
            qs = qs.filter(severity__in=allowed)
        if opts["keyword"]:
            kw = opts["keyword"]
            qs = qs.filter(Q(title__icontains=kw) | Q(abstract__icontains=kw))
        if opts["area"]:
            # Match if any affected_files starts with any --area prefix.
            area_q = Q()
            for area in opts["area"]:
                area_q |= Q(affected_files__icontains=area)
            qs = qs.filter(area_q)
        qs = qs.order_by("-priority_score", "-last_seen")[: int(opts["limit"])]
        rows = list(qs)

        self.stdout.write(
            f"[PAPER TRAIL SEARCH: {len(rows)} match(es)]"
        )
        for entry in rows:
            files = ",".join(entry.affected_files[:3]) if entry.affected_files else ""
            file_hint = f" — {files}" if files else ""
            self.stdout.write(
                f"  #{entry.pk} [{entry.status}/{entry.category}/{entry.severity}] "
                f"{entry.title[:80]}{file_hint}"
            )
