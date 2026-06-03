from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

from apps.core import backups


class BackupRetentionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.backup_dir = Path(settings.BASE_DIR) / "tmp" / "test-backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        for path in self.backup_dir.glob("*"):
            path.unlink()

    def test_unchanged_dump_reuses_latest_snapshot(self):
        snapshot = self._write_snapshot("snapshot-20260521-010000.dump", 5)
        with (
            patch("apps.core.backups.create_snapshot", return_value=snapshot),
            patch("apps.core.backups.prune_old_snapshots", return_value=[]),
            patch("apps.core.backups.disk_free_bytes", return_value=20),
        ):
            first = backups.run_backup_pass(backup_dir=self.backup_dir, keep_count=10)
            second = backups.run_backup_pass(backup_dir=self.backup_dir, keep_count=10)

        snapshots = backups.list_existing_snapshots(self.backup_dir)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(first["created"], second["created"])
        self.assertEqual(first["deleted_count"], 0)

    def test_byte_cap_prunes_oldest_snapshots(self):
        old = self._write_snapshot("snapshot-20260521-010000.dump", 5)
        middle = self._write_snapshot("snapshot-20260521-020000.dump", 5)
        newest = self._write_snapshot("snapshot-20260521-030000.dump", 5)

        deleted = backups.prune_old_snapshots(
            backup_dir=self.backup_dir,
            keep_count=2,
        )

        self.assertEqual([path.name for path in deleted], [old.name])
        self.assertFalse(old.exists())
        self.assertTrue(middle.exists())
        self.assertTrue(newest.exists())

    def test_eviction_refuses_project_root(self):
        with self.assertRaisesMessage(ValueError, "restore_from_snapshot is destructive"):
            backups.restore_from_snapshot(snapshot_path=Path(settings.BASE_DIR))

    def test_backup_db_now_routes_to_frequent_target(self):
        output = StringIO()
        with patch("apps.core.backups.run_backup_pass") as run_backup:
            run_backup.return_value = {"created": "snapshot.dump"}
            call_command("backup_db_now", stdout=output)

        self.assertEqual(run_backup.call_args.kwargs, {})
        self.assertEqual(json.loads(output.getvalue())["created"], "snapshot.dump")

    def _patched_dump(self, payload: bytes):
        def fake_dump(*, output_file, **_kwargs):
            output_file.write_bytes(payload)
            return True

        return patch.multiple(
            backups,
            _run_pg_dump=fake_dump,
            _database_content_checksum=lambda **_kwargs: "same-content",
            disk_free_bytes=lambda _path: 20 * 1024 * 1024 * 1024,
        )

    def _write_snapshot(self, name: str, size: int) -> Path:
        path = self.backup_dir / name
        path.write_bytes(os.urandom(size))
        return path
