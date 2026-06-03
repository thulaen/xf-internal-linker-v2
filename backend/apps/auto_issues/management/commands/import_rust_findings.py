from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.services.rust_findings import import_rust_report


class Command(BaseCommand):
    help = "Import speccheck JSON findings into deduped AutoIssue rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            action="append",
            required=True,
            help="Path to a speccheck JSON report.",
        )

    def handle(self, *args, **options):
        total_created = 0
        total_updated = 0
        for report_path in options["report"]:
            result = import_rust_report(report_path)
            total_created += result.created
            total_updated += result.updated
        self.stdout.write(
            f"[RUST FINDINGS IMPORTED: created={total_created} updated={total_updated}]"
        )
