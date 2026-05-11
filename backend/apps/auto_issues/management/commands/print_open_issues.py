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

    # Ordered the same way the 6-source [REGISTRY READ] marker prints the
    # per-source breakdown (agent / glitchtip / pyroscope / tempo / loki /
    # faro). Matches `.githooks/check-registry-read.py:NEW_MARKER_RE`.
    _SOURCE_ORDER = (
        AutoIssue.SOURCE_AGENT,
        AutoIssue.SOURCE_GLITCHTIP,
        AutoIssue.SOURCE_PYROSCOPE,
        AutoIssue.SOURCE_TEMPO,
        AutoIssue.SOURCE_LOKI,
        AutoIssue.SOURCE_FARO,
    )

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
            help=(
                "Restrict to one source "
                "(agent, glitchtip, pyroscope, tempo, loki, faro)."
            ),
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

        total = AutoIssue.objects.filter(status__in=self._OPEN_STATUSES).count()
        # All-source view also prints a one-line per-source breakdown so
        # an agent can copy it into the [REGISTRY READ ...] marker
        # without running --source six times.
        if not opts["source"]:
            counts = {
                s: AutoIssue.objects.filter(
                    status__in=self._OPEN_STATUSES, source=s,
                ).count()
                for s in self._SOURCE_ORDER
            }
            breakdown = " / ".join(
                f"{counts[s]} {s}" for s in self._SOURCE_ORDER
            )
            self.stdout.write(
                f"[REGISTRY READ: {total} open ({breakdown}), "
                f"showing top {len(rows)}]"
            )
        else:
            self.stdout.write(
                f"[REGISTRY READ: {total} open, "
                f"showing top {len(rows)}]"
            )
        for r in rows:
            files = ",".join(r.affected_files[:3]) if r.affected_files else ""
            file_hint = f" — {files}" if files else ""
            self.stdout.write(
                f"  #{r.id} [{r.source}/{r.severity}] {r.title[:80]}{file_hint}"
            )
