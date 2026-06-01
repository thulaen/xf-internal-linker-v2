"""Scrape postgres-exporter and file/resolve AutoIssues for health breaches.

Run on a schedule (auto_issues.pgexporter_findings_refresh) and on demand.
Supports --dry-run, which evaluates the metrics and reports how many findings
WOULD be filed without writing anything. The work and the output formatting
live in pgexporter_picker.py (directly unit-tested); this command is a thin
CLI wrapper.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.services.pgexporter_picker import (
    format_findings_result,
    pick_pgexporter_findings,
)


class Command(BaseCommand):
    help = "File AutoIssues for postgres-exporter health breaches."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--metrics-url", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        result = pick_pgexporter_findings(opts["metrics_url"], dry_run=opts["dry_run"])
        self.stdout.write(
            self.style.SUCCESS(format_findings_result(result, dry_run=opts["dry_run"]))
        )
