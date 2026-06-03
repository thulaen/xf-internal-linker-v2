"""Report whether the observability pipeline is feeding AutoIssues.

Read-only verification used by .githooks/check-observability-pipeline.py.
Prints a per-source freshness summary. In ``--strict`` mode it exits non-zero
when any source has been silent for the window; otherwise silence is reported
as a warning only (a quiet system is not necessarily a broken one).
"""

# xf: no_dry_run -- read-only verification command; makes no DB writes.

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import observability_pipeline as op


class Command(BaseCommand):
    help = "Verify each observability source has fed an AutoIssue recently."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when any source is silent for the window.",
        )

    def handle(self, *args, **options) -> None:
        hours = options["hours"]
        freshness = op.pipeline_freshness(hours=hours)
        silent = [f.source for f in freshness if f.is_silent]
        for f in freshness:
            state = "SILENT" if f.is_silent else f"{f.recent_count} recent"
            self.stdout.write(f"  {f.source}: {state}")
        self.stdout.write(
            f"[OBSERVABILITY PIPELINE: window={hours}h "
            f"silent={len(silent)}/{len(freshness)} sources={','.join(silent) or 'none'}]"
        )
        if options["strict"] and silent:
            raise CommandError(
                f"Observability sources silent for {hours}h: {', '.join(silent)}"
            )
