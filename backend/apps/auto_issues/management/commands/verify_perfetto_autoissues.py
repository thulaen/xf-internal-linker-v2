"""Stop commits when Perfetto-backed AutoIssues are unresolved."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import perfetto


class Command(BaseCommand):
    help = "Verify Perfetto AutoIssues stay under quota and are resolved before commit."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--max-open", type=int, default=10)
        parser.add_argument("--block-open", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            open_issues = perfetto.verify_perfetto_autoissues(
                max_open=options["max_open"],
                block_open=options["block_open"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"[PERFETTO AUTOISSUES VERIFIED: open={len(open_issues)} "
            f"max={options['max_open']}]"
        )
