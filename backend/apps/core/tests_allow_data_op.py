from __future__ import annotations

import json
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class _Cursor:
    def __init__(self) -> None:
        self.sql: list[tuple[str, list[str]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def execute(self, sql: str, params: list[str]) -> None:
        self.sql.append((sql, params))


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


class AllowDataOpTests(SimpleTestCase):
    def test_requires_confirmation(self):
        with self.assertRaisesMessage(CommandError, "--confirm is required"):
            call_command(
                "allow_data_op",
                "--op",
                "admin_delete",
                "--reason",
                "recovering a deliberately removed admin row",
            )

    def test_requires_plain_english_reason(self):
        with self.assertRaisesMessage(CommandError, "at least 20 characters"):
            call_command(
                "allow_data_op",
                "--op",
                "admin_delete",
                "--confirm",
                "--reason",
                "short",
            )

    def test_admin_delete_sets_local_setting_and_writes_audit(self):
        cursor = _Cursor()
        output = StringIO()
        with self._patched_command(cursor):
            call_command(
                "allow_data_op",
                "--op",
                "admin_delete",
                "--confirm",
                "--reason",
                "recovering admin after operator approved deletion",
                stdout=output,
            )
        self.assertEqual(
            cursor.sql,
            [("SET LOCAL xf.allow_admin_delete = %s", ["true"])],
        )
        audit = json.loads(Path(self.audit_path).read_text().strip())
        self.assertEqual(audit["op"], "admin_delete")
        self.assertIn("[DATA OP OVERRIDE:", output.getvalue())

    def test_bulk_delete_sets_local_setting(self):
        cursor = _Cursor()
        with self._patched_command(cursor):
            call_command(
                "allow_data_op",
                "--op",
                "bulk_delete",
                "--confirm",
                "--reason",
                "operator approved a one-time table recovery operation",
            )
        self.assertEqual(cursor.sql, [("SET LOCAL xf.allow_bulk_delete = %s", ["true"])])

    def _patched_command(self, cursor: _Cursor):
        tmp_dir = Path("tmp/test-allow-data-op")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = tmp_dir / "audit.jsonl"
        self.audit_path.unlink(missing_ok=True)
        return _patched_cursor(cursor, self.audit_path)


@contextmanager
def _patched_cursor(cursor: _Cursor, audit_path: Path):
    with override_settings(DATA_PROTECTION_OVERRIDE_LOG=audit_path):
        with patch(
            "apps.core.management.commands.allow_data_op.connection",
            _Connection(cursor),
        ):
            yield
