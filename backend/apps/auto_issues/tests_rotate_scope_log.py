"""Tests for explicit quality scope decision log rotation."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase
from django.utils import timezone


class RotateScopeLogTests(SimpleTestCase):
    def test_rotate_scope_log_archives_existing_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = root / "audit"
            audit.mkdir()
            log = audit / "scope_decisions.jsonl"
            log.write_text('{"decision":"keep"}\n', encoding="utf-8")
            output = StringIO()

            with mock.patch.object(
                timezone,
                "now",
                return_value=timezone.datetime(2026, 5, 28, 12, 30, 0),
            ):
                call_command("rotate_scope_log", repo_root=str(root), stdout=output)

            archive = audit / "scope_decisions-20260528-123000.jsonl"
            self.assertEqual(log.read_text(encoding="utf-8"), "")
            self.assertEqual(archive.read_text(encoding="utf-8"), '{"decision":"keep"}\n')
            self.assertIn("[SCOPE LOG ROTATED: archived=", output.getvalue())

    def test_rotate_scope_log_can_create_missing_empty_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            call_command(
                "rotate_scope_log",
                repo_root=str(root),
                keep_empty=True,
                stdout=output,
            )

            log = root / "audit" / "scope_decisions.jsonl"
            self.assertTrue(log.exists())
            self.assertIn("[SCOPE LOG ROTATED: skipped missing log]", output.getvalue())

    def test_rotate_scope_log_rejects_directory_log_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audit" / "scope_decisions.jsonl").mkdir(parents=True)

            with self.assertRaises(CommandError):
                call_command("rotate_scope_log", repo_root=str(root))
