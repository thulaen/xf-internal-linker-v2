"""Stop commits when CodeQL-backed AutoIssues are unresolved."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import codeql


class Command(BaseCommand):
    help = "Verify that CodeQL AutoIssues stay under quota and are resolved before commit."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--max-open", type=int, default=10)
        parser.add_argument("--block-open", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            open_issues = codeql.verify_codeql_autoissues(
                max_open=options["max_open"],
                block_open=options["block_open"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"[CODEQL AUTOISSUES VERIFIED: open={len(open_issues)} max={options['max_open']}]")
