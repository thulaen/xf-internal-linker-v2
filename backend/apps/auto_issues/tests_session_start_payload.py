"""Tests for cached agent session startup payloads."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.auto_issues.services.session_start_payload import (
    PayloadError,
    build_payload,
    extract_autoissue_lines,
    extract_marker_lines,
    read_helper_payload,
    write_payload,
)


class SessionStartPayloadServiceTests(SimpleTestCase):
    def test_extract_marker_lines_keeps_required_markers(self) -> None:
        text = (
            "plain body\n"
            "[REGISTRY READ: 1 open]\n"
            "  #1 detail\n"
            "[TDD PREFLIGHT: armed]"
        )

        self.assertEqual(
            extract_marker_lines(text),
            ["[REGISTRY READ: 1 open]", "[TDD PREFLIGHT: armed]"],
        )

    def test_extract_autoissue_lines_keeps_registry_block(self) -> None:
        text = (
            "[REGISTRY READ: 2 open]\n"
            "| ID | Source | Severity | Title | Files |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| #1879 | agent | high | observability signal degraded: tempo | - |\n"
            "| #1878 | agent | high | observability signal degraded: sonarqube | - |\n"
            "[CI FAILED RUNS READ: 0 latest]"
        )

        self.assertEqual(
            extract_autoissue_lines(text),
            [
                "[REGISTRY READ: 2 open]",
                "| ID | Source | Severity | Title | Files |",
                "| --- | --- | --- | --- | --- |",
                "| #1879 | agent | high | observability signal degraded: tempo | - |",
                "| #1878 | agent | high | observability signal degraded: sonarqube | - |",
            ],
        )

    def test_build_payload_includes_handoff_and_command_markers(self) -> None:
        now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
        outputs = {
            "print_open_issues": "[REGISTRY READ: 1 open]\n[CI FAILED RUNS READ: 0 latest]",
            "print_open_paper_trail": "[PAPER TRAIL READ: 0 open]",
            "print_open_snapshots": "[SNAPSHOTS READ: 0 snapshots]",
            "print_failed_github_actions": "[GH ACTIONS READ: 0 failures]",
            "read_sticky": "7b8d04510bf49e49",
            "preflight_tdd": "[TDD PREFLIGHT: armed]",
        }

        payload = build_payload(
            command_runner=lambda name, _args: outputs[name],
            handoff_reader=lambda: "# 2026-05-26 20:18 - Codex - Token refreshed",
            now=lambda: now,
        )

        self.assertIn("[HANDOFF READ: 2026-05-26 20:18 by Codex", payload.body)
        self.assertIn("[STICKY 1 READ:", payload.body)
        self.assertIn("[REGISTRY READ: 1 open]", payload.markers)
        self.assertIn("[REGISTRY READ: 1 open]", payload.autoissues)
        self.assertEqual(payload.version, 1)

    def test_write_payload_overwrites_one_json_line(self) -> None:
        now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
        payload = build_payload(
            command_runner=lambda _name, _args: "[REGISTRY READ: 0 open]",
            handoff_reader=lambda: "# 2026-05-26 20:18 - Codex - Token refreshed",
            now=lambda: now,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.jsonl"
            write_payload(path, payload)
            write_payload(path, payload)

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["version"], 1)

    @mock.patch("apps.auto_issues.services.session_start_payload.urlopen")
    def test_read_helper_payload_rejects_stale_payload(self, mocked_urlopen) -> None:
        stale = {
            "version": 1,
            "generated_at": "2026-05-26T11:00:00Z",
            "expires_at": "2026-05-26T11:05:00Z",
            "markers": [],
            "body": "old",
        }
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            json.dumps(stale).encode("utf-8")
        )

        with self.assertRaises(PayloadError):
            read_helper_payload(
                "http://startupd:8765/payload",
                timeout_seconds=0.1,
                now=lambda: datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc),
            )

    @mock.patch("apps.auto_issues.services.session_start_payload.urlopen")
    def test_read_helper_payload_preserves_autoissues(self, mocked_urlopen) -> None:
        current = {
            "version": 1,
            "generated_at": "2026-05-26T11:00:00Z",
            "expires_at": "2026-05-26T12:05:00Z",
            "markers": ["[REGISTRY READ: 1 open]"],
            "autoissues": ["[REGISTRY READ: 1 open]", "#1879 issue"],
            "body": "[REGISTRY READ: 1 open]\n#1879 issue",
        }
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            json.dumps(current).encode("utf-8")
        )

        payload = read_helper_payload(
            "http://startupd:8765/payload",
            timeout_seconds=0.1,
            now=lambda: datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(payload.autoissues[-1], "#1879 issue")

    @mock.patch("apps.auto_issues.management.commands.session_start_payload.read_helper_payload")
    def test_command_prints_cached_payload(self, mocked_read) -> None:
        mocked_read.return_value = SimpleNamespace(
            body="[HANDOFF READ: example]\n[REGISTRY READ: 0 open]",
        )
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out:
            call_command("session_start_payload", stdout=out)
            out.seek(0)
            text = out.read()

        self.assertIn("[HANDOFF READ: example]", text)
        self.assertIn("[REGISTRY READ: 0 open]", text)

    @mock.patch("apps.auto_issues.management.commands.session_start_payload.read_helper_payload")
    def test_command_fails_clearly_when_helper_fails(self, mocked_read) -> None:
        mocked_read.side_effect = PayloadError("cached startup payload is missing")

        with self.assertRaises(CommandError) as caught:
            call_command("session_start_payload")

        self.assertIn("cached startup payload is missing", str(caught.exception))

    def test_payload_expires_after_hourly_refresh_window(self) -> None:
        now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
        payload = build_payload(
            command_runner=lambda _name, _args: "[REGISTRY READ: 0 open]",
            handoff_reader=lambda: "# 2026-05-26 20:18 - Codex - Token refreshed",
            now=lambda: now,
        )

        self.assertEqual(payload.expires_at, now + timedelta(minutes=65))

    @mock.patch("apps.auto_issues.services.session_start_payload.write_payload")
    @mock.patch("apps.auto_issues.services.session_start_payload.build_payload")
    def test_auto_refresh_task_writes_latest_payload(self, mocked_build, mocked_write) -> None:
        from apps.auto_issues.tasks import refresh_session_start_payload

        mocked_build.return_value = SimpleNamespace(markers=["[REGISTRY READ: 0 open]"])

        result = refresh_session_start_payload()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["markers"], 1)
        mocked_write.assert_called_once()

    def test_auto_refresh_is_scheduled_hourly_before_payload_expires(self) -> None:
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE["auto-issues-session-start-payload-refresh"]

        self.assertEqual(entry["task"], "auto_issues.refresh_session_start_payload")
        self.assertEqual(entry["schedule"].run_every.total_seconds(), 3600)

    @mock.patch("apps.auto_issues.management.commands.refresh_session_start_payload.write_payload")
    @mock.patch("apps.auto_issues.management.commands.refresh_session_start_payload.build_payload")
    def test_refresh_command_writes_payload_to_requested_path(
        self,
        mocked_build,
        mocked_write,
    ) -> None:
        mocked_build.return_value = SimpleNamespace(markers=["[REGISTRY READ: 0 open]"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.jsonl"
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out:
                call_command("refresh_session_start_payload", path=str(path), stdout=out)
                out.seek(0)
                text = out.read()

        mocked_write.assert_called_once_with(path, mocked_build.return_value)
        self.assertIn("[SESSION START PAYLOAD REFRESHED: markers=1", text)

    @mock.patch("apps.auto_issues.services.session_start_payload.write_payload")
    @mock.patch("apps.auto_issues.services.session_start_payload.build_payload")
    def test_auto_refresh_task_skips_write_on_read_only_filesystem(
        self, mocked_build, mocked_write
    ) -> None:
        from apps.auto_issues.tasks import refresh_session_start_payload

        mocked_build.return_value = SimpleNamespace(markers=["[REGISTRY READ: 0 open]"])
        mocked_write.side_effect = OSError(30, "Read-only file system")

        result = refresh_session_start_payload()

        self.assertEqual(result["status"], "skipped")
        self.assertIn("read-only", result["reason"])
