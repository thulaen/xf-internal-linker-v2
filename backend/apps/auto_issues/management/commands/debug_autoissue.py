"""Print a compact AutoIssue health summary for agents and operators."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Show AutoIssue counts, duplicate fingerprints, and recent rows."

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
    rows = AutoIssue.objects.all()
    by_source = _count_by(rows, "source")
    by_status = _count_by(rows, "status")
    duplicates = (
        rows.exclude(canonical_fingerprint="")
        .values("canonical_fingerprint")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("-count")[:limit]
    )
    top_open = rows.order_by("-priority_score", "-last_seen")[:limit]
    recently_resolved = rows.filter(status=AutoIssue.STATUS_RESOLVED).order_by("-resolved_at")[
        :limit
    ]
    return {
        "total": rows.count(),
        "by_source": by_source,
        "by_status": by_status,
        "duplicates": list(duplicates),
        "top_open": [_issue_row(issue) for issue in top_open],
        "recently_resolved": [_issue_row(issue) for issue in recently_resolved],
    }


def _count_by(queryset, field: str) -> dict[str, int]:
    counts = queryset.values(field).annotate(count=Count("id")).order_by(field)
    return {row[field] or "<blank>": row["count"] for row in counts}


def _issue_row(issue: AutoIssue) -> dict:
    return {
        "id": issue.id,
        "source": issue.source,
        "status": issue.status,
        "severity": issue.severity,
        "title": issue.title,
        "priority_score": issue.priority_score,
        "lessons": issue.lessons_learned[:150],
    }


def _format_human(payload: dict) -> str:
    lines = [
        f"[DEBUG AUTOISSUE: counts={json.dumps(payload['by_source'], sort_keys=True)}]",
        "AutoIssue summary",
        f"Total rows: {payload['total']}",
        f"By source: {json.dumps(payload['by_source'], sort_keys=True)}",
        f"By status: {json.dumps(payload['by_status'], sort_keys=True)}",
        f"Duplicate fingerprint groups: {len(payload['duplicates'])}",
        "Top rows:",
    ]
    for row in payload["top_open"]:
        lines.append(f"- #{row['id']} {row['source']} {row['status']} {row['title']}")
    return "\n".join(lines)
