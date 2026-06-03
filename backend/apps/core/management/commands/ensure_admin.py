from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Create the admin superuser only when auth_user is empty."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm"] and not options["dry_run"]:
            raise CommandError("Pass --confirm to create admin, or --dry-run to inspect.")

        username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not password:
            raise CommandError("ADMIN_PASSWORD is empty; refusing to create admin.")

        User = get_user_model()
        count = User.objects.count()
        if count:
            raise CommandError(
                f"auth_user already has rows ({count}); refusing to overwrite users."
            )

        if options["dry_run"]:
            self.stdout.write(json.dumps({"created": False, "username": username}))
            return

        user = User._default_manager.create_superuser(
            username=username,
            email="",
            password=password,
        )
        _write_audit_log(username=username, user_id=user.id)
        self.stdout.write(json.dumps({"created": True, "username": username, "id": user.id}))


def _write_audit_log(*, username: str, user_id: int) -> None:
    path = Path(
        getattr(
            settings,
            "ADMIN_RECOVERY_AUDIT_LOG",
            Path(settings.BASE_DIR) / "audit" / "admin_recovery_log.jsonl",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "created_at": timezone.now().isoformat(),
        "username": username,
        "user_id": user_id,
        "reason": "auth_user was empty and admin recovery was confirmed",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
