"""Search resolved AutoIssue rows by area / keyword / fingerprint.

Used by every agent at session start AFTER `print_open_issues`. The
question this answers: "did anyone fix something in this area before,
and what did they learn?". Output is a compact list with one row per
match — id, last-resolved date, title, lessons_learned excerpt.

Examples:
    manage.py search_resolved_issues --area backend/apps/audit
    manage.py search_resolved_issues --keyword "fingerprint collision"
    manage.py search_resolved_issues --fingerprint <16-char-hash>

If no match is found the command exits 0 with a single "no prior
fixes found in this area" line — the absence of prior fixes is itself
information for the agent.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Search resolved AutoIssue rows by area / keyword / fingerprint."

    _DEFAULT_LIMIT = 10

    def add_arguments(self, parser):
        parser.add_argument(
            "--area",
            help=(
                "Repo-relative path or path prefix; matches anything in "
                "`affected_files`. Example: backend/apps/audit"
            ),
        )
        parser.add_argument(
            "--keyword",
            help=(
                "Free-text token to match against title / description / "
                "lessons_learned. Case-insensitive."
            ),
        )
        parser.add_argument(
            "--fingerprint",
            help="Exact fingerprint match (16-char hex). For dedup checks.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=self._DEFAULT_LIMIT,
            help=f"Max matches to print (default {self._DEFAULT_LIMIT}).",
        )

    def handle(self, *args, **opts):
        qs = AutoIssue.objects.filter(status=AutoIssue.STATUS_RESOLVED)
        if opts["fingerprint"]:
            qs = qs.filter(fingerprint=opts["fingerprint"])
        if opts["area"]:
            # JSONField icontains: matches any element containing the path.
            qs = qs.filter(affected_files__icontains=opts["area"])
        if opts["keyword"]:
            kw = opts["keyword"]
            qs = qs.filter(
                Q(title__icontains=kw)
                | Q(description__icontains=kw)
                | Q(lessons_learned__icontains=kw)
            )
        rows = list(qs.order_by("-resolved_at")[: opts["limit"]])

        if not rows:
            self.stdout.write("[RESOLVED SEARCH: 0 matches — no prior fixes found in this area]")
            return

        self.stdout.write(f"[RESOLVED SEARCH: {len(rows)} prior fix(es) — read these BEFORE rewriting]")
        for r in rows:
            date = r.resolved_at.strftime("%Y-%m-%d") if r.resolved_at else "????-??-??"
            files = ",".join(r.affected_files[:3]) if r.affected_files else "—"
            self.stdout.write(
                f"  #{r.id} ({date}) [{r.source}/{r.severity}] {r.title[:80]}"
            )
            if r.lessons_learned:
                # Print up to two lines of the lesson — first is the trap
                # description, second is typically the fix shape.
                first_two = "\n      ".join(
                    r.lessons_learned.strip().splitlines()[:2]
                )
                self.stdout.write(f"      lesson: {first_two}")
            self.stdout.write(f"      files: {files}")
