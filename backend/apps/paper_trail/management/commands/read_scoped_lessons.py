# xf: no_dry_run -- read-only command; just prints scoped lessons. No state mutation.
"""manage.py read_scoped_lessons — scoped lesson lookup before commit.

Emits `[SCOPED LESSONS READ: <N> lessons in <areas>]` so the
.githooks/check-scoped-lessons.py hook can validate the agent ran the lookup.

Total lessons surfaced across all `--area` arguments is HARD-CAPPED
(default 10). Lessons are de-duplicated by autoissue_id and sorted by
(severity desc, resolved_at_unix desc) so the most relevant items
appear first. The picker + ART index therefore surface the top 10
globally-relevant lessons regardless of how many areas are passed.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.concept_tags import build_tag_query, collect_and_validate_tags
from apps.auto_issues.models import AutoIssue
from apps.paper_trail.services import lesson_index as svc


class Command(BaseCommand):
    help = (
        "Look up resolved-AutoIssue lessons for one or more repo-relative "
        "paths; surfaces the top-N most relevant globally (default 10 total)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--area", action="append", default=[],
            help="Repo-relative path prefix; pass multiple times.",
        )
        parser.add_argument(
            "--limit", type=int, default=10,
            help=("TOTAL cap across all areas (default 10). After dedup + "
                  "severity sort, at most this many lessons are emitted "
                  "regardless of how many --area flags were passed."),
        )
        parser.add_argument(
            "--tag",
            action="append",
            default=[],
            help="Approved concept tag; repeat for more than one.",
        )

    def handle(self, *args, **opts):
        areas = opts["area"] or [""]
        cap = max(0, int(opts["limit"]))
        tags = collect_and_validate_tags(opts, key="tag")

        # Pull up to `cap` candidates per area, then merge, dedup, sort, cap.
        seen: dict[int, dict] = {}
        per_area_counts: dict[str, int] = {}
        for area in areas:
            hits = svc.scoped_find(area, limit=cap)
            per_area_counts[area] = len(hits)
            for h in hits:
                aid = h["autoissue_id"]
                if aid not in seen:
                    seen[aid] = {**h, "_area": area}
        for h in _tagged_lessons(tags, limit=cap):
            aid = h["autoissue_id"]
            if aid not in seen:
                seen[aid] = h

        merged = sorted(
            seen.values(),
            key=lambda r: (
                -int(r.get("severity") or 0),
                -int(r.get("resolved_at_unix") or 0),
            ),
        )[:cap]

        for area in areas:
            self.stdout.write(
                f"# {area or '(repo root)'}: "
                f"{per_area_counts.get(area, 0)} candidate lessons"
            )

        self.stdout.write(f"# top {len(merged)} lessons (cap={cap}):")
        for h in merged:
            self.stdout.write(
                f"  #{h['autoissue_id']} sev={h['severity']} "
                f"resolved_at={h['resolved_at_unix']} area={h.get('_area','')}"
            )

        marker = f"[SCOPED LESSONS READ: {len(merged)} lessons in {','.join(areas)}"
        if tags:
            marker += f" tags={','.join(tags)}"
        self.stdout.write(f"{marker}]")


def _tagged_lessons(tags: list[str], *, limit: int) -> list[dict]:
    if not tags or limit <= 0:
        return []
    severity_rank = {
        AutoIssue.SEVERITY_LOW: 0,
        AutoIssue.SEVERITY_MEDIUM: 1,
        AutoIssue.SEVERITY_HIGH: 2,
        AutoIssue.SEVERITY_CRITICAL: 3,
    }
    rows = (
        AutoIssue.objects.filter(status=AutoIssue.STATUS_RESOLVED)
        .filter(build_tag_query(tags))
        .order_by("-resolved_at")[:limit]
    )
    return [
        {
            "autoissue_id": row.id,
            "lesson_hash": hash(row.title) & 0xFFFFFFFFFFFFFFFF,
            "severity": severity_rank.get(row.severity, 1),
            "resolved_at_unix": int(row.resolved_at.timestamp()) if row.resolved_at else 0,
            "_area": f"tags={','.join(tags)}",
        }
        for row in rows
    ]
