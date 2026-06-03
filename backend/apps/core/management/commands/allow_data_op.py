"""Audit a one-time protected database operation override."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


SETTING_BY_OP = {
    "admin_delete": "xf.allow_admin_delete",
    "bulk_delete": "xf.allow_bulk_delete",
}


class Command(BaseCommand):
    help = "Record and enable a one-transaction protected data operation override."

    def add_arguments(self, parser):
        parser.add_argument("--op", choices=sorted(SETTING_BY_OP), required=True)
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("--confirm is required for protected data overrides.")

        reason = options["reason"].strip()
        if len(reason) < 20:
            raise CommandError("Override reason must be at least 20 characters.")

        op = options["op"]
        setting_name = SETTING_BY_OP[op]
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL {setting_name} = %s", ["true"])

        audit_path = Path(
            getattr(
                settings,
                "DATA_PROTECTION_OVERRIDE_LOG",
                Path(settings.BASE_DIR) / "audit" / "data_protection_override_log.jsonl",
            )
        )
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_row = {
            "created_at": datetime.now(UTC).isoformat(),
            "op": op,
            "setting": setting_name,
            "reason": reason,
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(audit_row, sort_keys=True) + "\n")

        self.stdout.write(f"[DATA OP OVERRIDE: op={op} setting={setting_name} audited=yes]")
