from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings


class EnsureAdminCommandTests(TestCase):
    def setUp(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL xf.allow_admin_delete = 'true'")
        get_user_model().objects.all().delete()

    def test_when_auth_user_empty_then_confirm_creates_admin(self):
        with TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "admin_recovery_log.jsonl"
            with override_settings(ADMIN_RECOVERY_AUDIT_LOG=str(audit_path)):
                with patch.dict(
                    "os.environ",
                    {
                        "ADMIN_USERNAME": "admin",
                        "ADMIN_PASSWORD": "xyxy1022_XF_django",
                    },
                ):
                    output = StringIO()
                    call_command("ensure_admin", "--confirm", stdout=output)

            user = get_user_model().objects.get(username="admin")
            self.assertTrue(user.is_superuser)
            self.assertTrue(user.check_password("xyxy1022_XF_django"))
            self.assertIn('"created": true', output.getvalue())
            self.assertEqual(len(audit_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_when_users_exist_then_command_refuses_overwrite(self):
        get_user_model().objects.create_user(username="existing")

        with patch.dict("os.environ", {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "secret"}):
            with self.assertRaisesMessage(CommandError, "auth_user already has rows"):
                call_command("ensure_admin", "--confirm")

    def test_when_password_missing_then_command_refuses(self):
        with patch.dict("os.environ", {"ADMIN_USERNAME": "admin"}, clear=True):
            with self.assertRaisesMessage(CommandError, "ADMIN_PASSWORD is empty"):
                call_command("ensure_admin", "--confirm")

    def test_when_dry_run_then_no_user_is_written(self):
        with patch.dict("os.environ", {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "secret"}):
            output = StringIO()
            call_command("ensure_admin", "--dry-run", stdout=output)

        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertFalse(json.loads(output.getvalue())["created"])
