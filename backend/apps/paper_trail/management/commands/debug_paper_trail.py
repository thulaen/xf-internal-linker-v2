"""Print a compact PaperTrail health summary for agents and operators."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.paper_trail.models import PaperTrailEntry


class Command(BaseCommand):
    help = "Show PaperTrail counts, duplicate fingerprints, and recent rows."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        limit = max(0, options["limit"])
        payload = _build_payload(limit)
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        self.stdout.write(_format_human(payload))


def _build_payload(limit: int) -> dict:
    rows = PaperTrailEntry.objects.all()
    duplicates = (
        rows.exclude(canonical_fingerprint="")
        .values("canonical_fingerprint")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")[:limit]
    )
    top_open = rows.order_by("-priority_score", "-last_seen")[:limit]
    recently_resolved = rows.filter(status=PaperTrailEntry.STATUS_RESOLVED).order_by(
        "-resolved_at"
    )[:limit]
    return {
        "total": rows.count(),
        "by_category": _count_by(rows, "category"),
        "by_status": _count_by(rows, "status"),
        "duplicates": list(duplicates),
        "top_open": [_entry_row(entry) for entry in top_open],
        "recently_resolved": [_entry_row(entry) for entry in recently_resolved],
    }


def _count_by(queryset, field: str) -> dict[str, int]:
    counts = queryset.values(field).annotate(count=Count("id")).order_by(field)
    return {row[field] or "<blank>": row["count"] for row in counts}


def _entry_row(entry: PaperTrailEntry) -> dict:
    return {
        "id": entry.id,
        "category": entry.category,
        "status": entry.status,
        "severity": entry.severity,
        "title": entry.title,
        "priority_score": entry.priority_score,
        "lessons": entry.resolution_lessons[:150],
    }


def _format_human(payload: dict) -> str:
    lines = [
        f"[DEBUG PAPER TRAIL: counts={json.dumps(payload['by_category'], sort_keys=True)}]",
        "PaperTrail summary",
        f"Total rows: {payload['total']}",
        f"By category: {json.dumps(payload['by_category'], sort_keys=True)}",
        f"By status: {json.dumps(payload['by_status'], sort_keys=True)}",
        f"Duplicate fingerprint groups: {len(payload['duplicates'])}",
        "Top rows:",
    ]
    for row in payload["top_open"]:
        lines.append(f"- #{row['id']} {row['category']} {row['status']} {row['title']}")
    return "\n".join(lines)
