from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.audit.services import test_database_shards


class TestDatabaseShardHelperTests(SimpleTestCase):
    def test_builds_safe_timestamped_shard_database_name(self) -> None:
        name = test_database_shards.build_shard_database_name(
            "Run 42 / main",
            3,
            now=datetime(2026, 6, 17, 9, 30, 0, tzinfo=UTC),
        )

        self.assertEqual(name, "xf_t_20260617093000_run_42_main_s3")

    def test_rejects_unsafe_database_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe Postgres database name"):
            test_database_shards.validate_database_name("bad-name;drop")

    def test_selects_only_expired_shard_database_names(self) -> None:
        old_name = "xf_t_20000101000000_old_run_s0"
        new_name = test_database_shards.build_shard_database_name("new", 0)
        names = [old_name, new_name, "postgres"]

        expired = test_database_shards.expired_shard_databases(
            names,
            max_age=timedelta(hours=12),
        )

        self.assertEqual(expired, [old_name])


class TestDatabaseShardCommandTests(SimpleTestCase):
    def test_cleanup_dry_run_lists_expired_without_drop(self) -> None:
        out = StringIO()
        with patch.object(
            test_database_shards,
            "list_shard_databases",
            return_value=["xf_t_20000101000000_old_run_s0"],
        ), patch.object(test_database_shards, "drop_database") as drop_database:
            call_command(
                "cleanup_test_shard_databases",
                "--dry-run",
                stdout=out,
            )

        drop_database.assert_not_called()
        self.assertIn("expired=1", out.getvalue())

    def test_template_rebuild_dry_run_does_not_touch_database(self) -> None:
        out = StringIO()
        with patch.object(test_database_shards, "drop_database") as drop_database:
            call_command("rebuild_test_db_template", "--dry-run", stdout=out)

        drop_database.assert_not_called()
        self.assertIn("TEST DB TEMPLATE DRY-RUN", out.getvalue())
