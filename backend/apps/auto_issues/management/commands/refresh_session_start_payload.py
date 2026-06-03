"""Refresh the cached session-start payload outside the chat path."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.auto_issues.services.session_start_payload import (
    build_payload,
    default_payload_path,
    write_payload,
)


class Command(BaseCommand):
    help = "Run live startup checks and write the cached startup payload."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=None,
            help="Optional payload cache path. Defaults to audit/session_start_payload.jsonl.",
        )

    def handle(self, *args, **options) -> None:
        path = default_payload_path() if options["path"] is None else Path(options["path"])
        payload = build_payload()
        write_payload(path, payload)
        self.stdout.write(
            f"[SESSION START PAYLOAD REFRESHED: markers={len(payload.markers)} path={path}]"
        )
