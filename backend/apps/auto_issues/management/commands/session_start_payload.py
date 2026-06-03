"""Print the cached session-start payload served by startupd."""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services.session_start_payload import (
    DEFAULT_TIMEOUT_SECONDS,
    PayloadError,
    read_helper_payload,
)


class Command(BaseCommand):
    help = "Print the cached session-start payload within the hard timeout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=os.environ.get("XF_STARTUPD_URL", "http://startupd:8765/payload"),
            help="startupd payload URL.",
        )
        parser.add_argument(
            "--timeout-seconds",
            type=float,
            default=DEFAULT_TIMEOUT_SECONDS,
            help="Hard timeout for reading startupd.",
        )

    def handle(self, *args, **options) -> None:
        try:
            payload = read_helper_payload(
                options["url"],
                timeout_seconds=options["timeout_seconds"],
            )
        except PayloadError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(payload.body)
