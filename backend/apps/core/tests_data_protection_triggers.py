from __future__ import annotations

from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase


TRIGGER_MIGRATION = import_module("apps.core.migrations.0021_data_protection_triggers")


class DataProtectionTriggerTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(TRIGGER_MIGRATION.REVERSE_SQL)
            cursor.execute(TRIGGER_MIGRATION.FORWARD_SQL)
        user, _created = get_user_model().objects.get_or_create(username="admin")
        user.is_staff = True
        user.is_superuser = True
        user.set_password("xyxy1022_XF_django")
        user.save()

    def tearDown(self) -> None:
        with connection.cursor() as cursor:
            db_name = str(connection.settings_dict.get("NAME", ""))
            if db_name.startswith("test_"):
                cursor.execute(TRIGGER_MIGRATION.REVERSE_SQL)
            else:
                cursor.execute(TRIGGER_MIGRATION.FORWARD_SQL)

    def test_admin_delete_is_blocked_by_database(self):
        with self.assertRaisesMessage(DatabaseError, "admin user is protected"):
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM auth_user WHERE username = 'admin'")
        connection.rollback()
        self.assertTrue(get_user_model().objects.filter(username="admin").exists())

    def test_admin_delete_override_can_be_used_inside_rollback(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL xf.allow_admin_delete = 'true'")
                    cursor.execute("DELETE FROM auth_user WHERE username = 'admin'")
                raise RuntimeError("rollback test delete")
        self.assertTrue(get_user_model().objects.filter(username="admin").exists())

    def test_autoissue_truncate_is_blocked_by_database(self):
        with self.assertRaisesMessage(DatabaseError, "AutoIssue table is protected"):
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE auto_issues_autoissue CASCADE")
        connection.rollback()

    def test_papertrail_truncate_is_blocked_by_database(self):
        with self.assertRaisesMessage(DatabaseError, "PaperTrail table is protected"):
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE paper_trail_papertrailentry")
        connection.rollback()
