"""Verify the always-on, drought-aware "fix N" quota for one AutoIssue source.

Read-only: counts open + resolved-this-session issues for the source and
applies always_on_quota_status. A clean source (open < threshold) passes; a
source with >= threshold open passes only when >= threshold were resolved
after the cutoff. Used by .githooks/check-always-on-quota.py.

# xf: no_dry_run -- read-only verification command; it never writes.
"""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.always_on_quota import (
    DEFAULT_THRESHOLD,
    always_on_quota_status,
)


class Command(BaseCommand):
    help = "Verify the always-on fix-N quota for one AutoIssue source."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--source", required=True, help="AutoIssue source slug, e.g. prometheus.")
        parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
        parser.add_argument(
            "--resolved-after",
            help="Cutoff (YYYY-MM-DD HH:MM); only resolutions after it count.",
        )

    def handle(self, *args, **opts) -> None:
        source = opts["source"]
        threshold = opts["threshold"]
        cutoff = _parse_cutoff(opts.get("resolved_after"))

        open_count = (
            AutoIssue.objects.filter(source=source)
            .exclude(status=AutoIssue.STATUS_RESOLVED)
            .count()
        )
        resolved_qs = AutoIssue.objects.filter(
            source=source,
            status=AutoIssue.STATUS_RESOLVED,
            lessons_learned__gt="",
            resolved_at__isnull=False,
        )
        if cutoff is not None:
            resolved_qs = resolved_qs.filter(resolved_at__gt=cutoff)
        resolved_count = resolved_qs.count()

        status = always_on_quota_status(
            open_count=open_count, resolved_count=resolved_count, threshold=threshold
        )
        if not status.ok:
            raise CommandError(
                f"FAIL check-always-on-quota [{source}]: {status.message}\n"
                f"WHY: the always-on quota blocks commits while {threshold}+ "
                f"{source} AutoIssues are open.\n"
                f"UNBLOCK: resolve {status.short} more {source} AutoIssue(s) "
                "with two-part 'Trap: ... Fix shape: ...' lessons via "
                "`manage.py resolve_autoissue`, then re-commit."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"[ALWAYS-ON QUOTA VERIFIED: source={source} open={open_count} "
                f"resolved={resolved_count} threshold={threshold}]"
            )
        )


def _parse_cutoff(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise CommandError("--resolved-after must use YYYY-MM-DD HH:MM") from exc
    return timezone.make_aware(parsed, timezone.get_current_timezone())
