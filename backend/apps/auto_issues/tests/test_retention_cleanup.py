"""Tests for apps.auto_issues.services.retention_cleanup.

Covers Bug 7 (retention): a failure in one cleanup routine must not
prevent the other routines from running.
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import retention_cleanup
from apps.auto_issues.services.retention_cleanup import _cleanup_pyroscope_blocks
from apps.auto_issues.services.retention_cleanup import run_retention_cleanup


class RetentionIsolationTests(TestCase):
    def test_pyroscope_failure_does_not_block_audit_or_auto_issues(self):
        """Bug 7 fix: each cleanup wrapped independently so one failure does not silence the rest."""
        with patch(
            "apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
            side_effect=RuntimeError("disk emergency"),
        ):
            result = run_retention_cleanup()

        # Without the fix, RuntimeError propagates and the dict is never built.
        # With the fix, the other two keys are present with valid results.
        self.assertIn("audit_errorlog", result)
        self.assertIn("auto_issues", result)

    def test_audit_errorlog_failure_does_not_block_auto_issues(self):
        with patch(
            "apps.auto_issues.services.retention_cleanup._cleanup_audit_errorlog",
            side_effect=RuntimeError("db down"),
        ):
            result = run_retention_cleanup()

        self.assertIn("auto_issues", result)

    def test_all_cleanups_run_returns_expected_keys(self):
        with (
            patch("apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
                  return_value={"status": "skipped", "reason": "not mounted"}),
            patch("apps.auto_issues.services.retention_cleanup._cleanup_audit_errorlog",
                  return_value={"status": "ok", "deleted_count": 0, "retention_days": 90}),
            patch("apps.auto_issues.services.retention_cleanup._cleanup_auto_issues_resolved",
                  return_value={"status": "ok", "deleted_count": 0, "retention_days": 180}),
        ):
            result = run_retention_cleanup()

        self.assertEqual(result["status"], "ok")
        self.assertIn("pyroscope", result)
        self.assertIn("audit_errorlog", result)
        self.assertIn("auto_issues", result)

    def test_failed_cleanup_status_recorded_in_result(self):
        """When a cleanup fails, the result dict records the error rather than hiding it."""
        with patch(
            "apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
            side_effect=RuntimeError("boom"),
        ):
            result = run_retention_cleanup()

        pyro = result.get("pyroscope", {})
        self.assertEqual(pyro.get("status"), "error")


class ResolvedAutoIssueCleanupTests(TestCase):
    def test_resolved_rows_older_than_180_days_are_deleted(self):
        old_cutoff = timezone.now() - timedelta(days=200)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="cleanup-old-1",
            fingerprint="cleanup-old-fp-1",
            title="Old resolved issue",
            severity=AutoIssue.SEVERITY_LOW,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=old_cutoff,
        )
        recent_cutoff = timezone.now() - timedelta(days=30)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="cleanup-recent-1",
            fingerprint="cleanup-recent-fp-1",
            title="Recent resolved issue",
            severity=AutoIssue.SEVERITY_LOW,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=recent_cutoff,
        )

        with (
            patch("apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
                  return_value={"status": "skipped"}),
            patch("apps.auto_issues.services.retention_cleanup._cleanup_audit_errorlog",
                  return_value={"status": "ok", "deleted_count": 0, "retention_days": 90}),
        ):
            result = run_retention_cleanup()

        self.assertEqual(result["auto_issues"]["deleted_count"], 1)
        self.assertFalse(
            AutoIssue.objects.filter(external_id="cleanup-old-1").exists()
        )
        self.assertTrue(
            AutoIssue.objects.filter(external_id="cleanup-recent-1").exists()
        )

    def test_open_issues_not_deleted(self):
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="cleanup-open-1",
            fingerprint="cleanup-open-fp-1",
            title="Open issue",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_OPEN,
        )

        with (
            patch("apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
                  return_value={"status": "skipped"}),
            patch("apps.auto_issues.services.retention_cleanup._cleanup_audit_errorlog",
                  return_value={"status": "ok", "deleted_count": 0, "retention_days": 90}),
        ):
            result = run_retention_cleanup()

        self.assertEqual(result["auto_issues"]["deleted_count"], 0)
        self.assertTrue(
            AutoIssue.objects.filter(external_id="cleanup-open-1").exists()
        )

    def test_cleanup_returns_dict_with_status_ok_and_count(self):
        with (
            patch("apps.auto_issues.services.retention_cleanup._cleanup_pyroscope_blocks",
                  return_value={"status": "skipped"}),
            patch("apps.auto_issues.services.retention_cleanup._cleanup_audit_errorlog",
                  return_value={"status": "ok", "deleted_count": 0, "retention_days": 90}),
        ):
            result = run_retention_cleanup()

        ai = result["auto_issues"]
        self.assertEqual(ai["status"], "ok")
        self.assertIn("deleted_count", ai)
        self.assertIn("retention_days", ai)
        self.assertEqual(ai["retention_days"], 180)


class PyroscopeBlocksCleanupTests(TestCase):
    """Direct tests for _cleanup_pyroscope_blocks filesystem logic."""

    def _make_old_file(self, directory: Path, name: str) -> Path:
        path = directory / name
        path.write_bytes(b"block data")
        old_mtime = time.time() - (91 * 86400)  # 91 days ago — beyond 90-day retention
        os.utime(path, (old_mtime, old_mtime))
        return path

    def test_old_files_are_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = self._make_old_file(Path(tmpdir), "old_block.bin")
            new_file = Path(tmpdir) / "new_block.bin"
            new_file.write_bytes(b"fresh data")

            with patch("apps.auto_issues.services.retention_cleanup._PYROSCOPE_DATA_PATH", tmpdir):
                result = _cleanup_pyroscope_blocks()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["deleted_count"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_directory_entries_skipped_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            with patch("apps.auto_issues.services.retention_cleanup._PYROSCOPE_DATA_PATH", tmpdir):
                result = _cleanup_pyroscope_blocks()

            self.assertTrue(subdir.exists())
            self.assertEqual(result["deleted_count"], 0)

    def test_oserror_on_unlink_is_counted_as_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = self._make_old_file(Path(tmpdir), "locked.bin")

            with patch.object(Path, "unlink", side_effect=OSError("locked")):
                with patch("apps.auto_issues.services.retention_cleanup._PYROSCOPE_DATA_PATH", tmpdir):
                    result = _cleanup_pyroscope_blocks()

            self.assertEqual(result["failed_count"], 1)
            self.assertTrue(old_file.exists())

    def test_volume_not_mounted_returns_skipped(self):
        with patch("apps.auto_issues.services.retention_cleanup._PYROSCOPE_DATA_PATH", "/nonexistent-volume-xyz"):
            result = _cleanup_pyroscope_blocks()
        self.assertEqual(result["status"], "skipped")
