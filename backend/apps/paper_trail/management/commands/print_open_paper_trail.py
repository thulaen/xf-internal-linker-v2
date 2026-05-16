"""manage.py print_open_paper_trail — mandatory opening-ritual marker."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import picker
from apps.paper_trail.services.priority import refresh_priority_scores


class Command(BaseCommand):
    help = "Print the open paper-trail summary + top-10 marker for the opening ritual."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--no-refresh-scores", action="store_true")

    def handle(self, *args, **opts):
        if not opts["no_refresh_scores"]:
            refresh_priority_scores()

        total = picker.total_open()
        counts = picker.count_by_category()
        top = picker.pick_top_n(int(opts["limit"]))

        # Emit the 16-source breakdown in the canonical order.
        breakdown = " / ".join(
            f"{counts.get(cat, 0)} {cat}"
            for cat, _label in PaperTrailEntry.CATEGORY_CHOICES
        )

        if not top:
            picks = "(drought; no open entries — file new entries per docs/PAPER-TRAIL.md)"
        elif len(top) < int(opts["limit"]):
            picks_list = ", ".join(f"#{e.pk}" for e in top)
            picks = f"{picks_list} (drought; file the remainder per docs/PAPER-TRAIL.md)"
        else:
            picks = ", ".join(f"#{e.pk}" for e in top)

        self.stdout.write(
            f"[PAPER TRAIL READ: {total} open ({breakdown}) — picked: {picks}]"
        )

        for entry in top:
            files = ",".join(entry.affected_files[:3]) if entry.affected_files else ""
            file_hint = f" — {files}" if files else ""
            self.stdout.write(
                f"  #{entry.pk} [{entry.category}/{entry.severity}] "
                f"{entry.title[:80]}{file_hint}"
            )
