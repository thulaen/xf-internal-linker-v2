"""manage.py read_scoped_lessons — scoped lesson lookup before commit.

Emits `[SCOPED LESSONS READ: <N> lessons in <areas>]` so the
.githooks/check-scoped-lessons.py hook can validate the agent ran the lookup.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.paper_trail.services import lesson_index as svc


class Command(BaseCommand):
    help = "Look up resolved-AutoIssue lessons for one or more repo-relative paths."

    def add_arguments(self, parser):
        parser.add_argument("--area", action="append", default=[],
                            help="Repo-relative path prefix; pass multiple times.")
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **opts):
        areas = opts["area"] or [""]
        total = 0
        for area in areas:
            hits = svc.scoped_find(area, limit=opts["limit"])
            total += len(hits)
            self.stdout.write(f"# {area or '(repo root)'}: {len(hits)} lessons")
            for h in hits:
                self.stdout.write(
                    f"  #{h['autoissue_id']} sev={h['severity']} "
                    f"resolved_at={h['resolved_at_unix']}"
                )
        self.stdout.write(
            f"[SCOPED LESSONS READ: {total} lessons in {','.join(areas)}]"
        )
