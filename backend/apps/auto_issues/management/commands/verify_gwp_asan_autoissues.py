"""Stop commits when GWP-ASan-backed AutoIssues are unresolved."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import gwp_asan


class Command(BaseCommand):
    help = "Verify GWP-ASan AutoIssues stay under quota and are resolved before commit."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--max-open", type=int, default=10)
        parser.add_argument("--block-open", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            open_issues = gwp_asan.verify_gwp_asan_autoissues(
                max_open=options["max_open"],
                block_open=options["block_open"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"[GWP-ASAN AUTOISSUES VERIFIED: open={len(open_issues)} "
            f"max={options['max_open']}]"
        )
