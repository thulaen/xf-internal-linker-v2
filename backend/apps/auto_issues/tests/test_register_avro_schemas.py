"""Tests for the register_avro_schemas management command.

Given the canonical .avsc schemas under services/sidecars/schemas/,
When register_avro_schemas runs,
Then each schema is validated and registered with schemard (or listed in
dry-run mode without contacting the sidecar).
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.auto_issues.management.commands import register_avro_schemas as cmd


class RegisterAvroSchemasTests(SimpleTestCase):
    def test_schemas_dir_has_canonical_files(self) -> None:
        files = sorted(p.name for p in cmd._schemas_dir().glob("*.avsc"))
        self.assertIn("auto_issue.v1.avsc", files)
        self.assertIn("paper_trail_entry.v1.avsc", files)
        self.assertIn("snapshot.v1.avsc", files)

    def test_dry_run_lists_without_client(self) -> None:
        out = StringIO()
        call_command("register_avro_schemas", "--dry-run", stdout=out)
        text = out.getvalue()
        self.assertIn("would register: auto_issue.v1", text)
        self.assertIn("dry-run", text)

    def test_registers_each_schema_via_client(self) -> None:
        fake_client = mock.Mock()
        fake_client.register.side_effect = lambda **kw: mock.Mock(
            subject=kw["subject"], version=1
        )
        with mock.patch(
            "apps.auto_issues._sidecars.schemard_client.SchemardClient",
            return_value=fake_client,
        ):
            out = StringIO()
            call_command("register_avro_schemas", stdout=out)
        self.assertIn("AVRO SCHEMAS REGISTERED", out.getvalue())
        # One register() call per .avsc file (at least the three canonical ones).
        self.assertGreaterEqual(fake_client.register.call_count, 3)

    def test_invalid_json_raises(self) -> None:
        # Point the command at a temp dir containing a broken schema.
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "broken.v1.avsc"
            bad.write_text("{not json", encoding="utf-8")
            with mock.patch.object(cmd, "_schemas_dir", return_value=Path(d)):
                with self.assertRaisesMessage(CommandError, "not valid JSON"):
                    call_command("register_avro_schemas", "--dry-run", stdout=StringIO())
