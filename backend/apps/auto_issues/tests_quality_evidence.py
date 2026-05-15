"""Tests for compact quality evidence and disposable artifact cleanup."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, QualityEvidence, QualityRawSnippet
from apps.auto_issues.services.quality_artifacts import (
    find_quality_artifacts,
    prune_quality_artifacts,
)
from apps.auto_issues.services.quality_evidence import (
    QualityEvidenceInput,
    prune_old_raw_snippets,
    record_quality_evidence,
    should_capture_weekly_raw_snippet,
)


def _payload(**overrides) -> QualityEvidenceInput:
    defaults = {
        "check_type": QualityEvidence.CHECK_MUTATION,
        "status": QualityEvidence.STATUS_FAILED,
        "tool_name": "mutmut",
        "tool_version": "2.5.1",
        "command": "mutmut run",
        "summary": "Mutation check failed. Future agents should add a focused test.",
        "source_hash": "abc123",
        "file_path": "backend/apps/demo.py",
        "failure_fingerprint": "mutmut:demo:10",
        "target_percent": 100.0,
        "actual_percent": 99.0,
        "details": {"survivor": "x > y changed to x >= y"},
    }
    defaults.update(overrides)
    return QualityEvidenceInput(**defaults)


class QualityEvidenceTests(TestCase):
    def setUp(self) -> None:
        QualityEvidence.objects.all().delete()
        QualityRawSnippet.objects.all().delete()
        AutoIssue.objects.all().delete()

    def test_failed_evidence_creates_autoissue(self) -> None:
        evidence = record_quality_evidence(_payload())

        self.assertEqual(QualityEvidence.objects.count(), 1)
        self.assertIsNotNone(evidence.auto_issue)
        self.assertEqual(evidence.auto_issue.source, AutoIssue.SOURCE_MUTATION)
        self.assertEqual(evidence.auto_issue.category.key, "correctness")

    def test_failed_tool_readiness_evidence_creates_tooling_autoissue(self) -> None:
        evidence = record_quality_evidence(
            _payload(
                check_type=QualityEvidence.CHECK_TOOL_READINESS,
                tool_name="compiled-tools",
                failure_fingerprint="tool-readiness:compiled-tools:failed",
            )
        )

        self.assertEqual(evidence.auto_issue.category.key, "tooling")

    def test_duplicate_evidence_updates_one_row(self) -> None:
        first = record_quality_evidence(_payload())
        second = record_quality_evidence(_payload(actual_percent=98.0))

        self.assertEqual(first.id, second.id)
        second.refresh_from_db()
        self.assertEqual(second.occurrence_count, 2)
        self.assertEqual(QualityEvidence.objects.count(), 1)
        self.assertEqual(AutoIssue.objects.count(), 1)

    def test_changed_source_hash_creates_new_evidence_version(self) -> None:
        record_quality_evidence(_payload(source_hash="old"))
        record_quality_evidence(_payload(source_hash="new"))

        self.assertEqual(QualityEvidence.objects.count(), 2)
        self.assertEqual(AutoIssue.objects.count(), 1)

    def test_every_check_type_creates_and_updates_one_evidence_row(self) -> None:
        for check_type, _label in QualityEvidence.CHECK_CHOICES:
            payload = _payload(
                check_type=check_type,
                tool_name=f"tool-{check_type}",
                command=f"run {check_type}",
                file_path=f"backend/apps/{check_type}.py",
                failure_fingerprint=f"{check_type}:failure",
            )
            first = record_quality_evidence(payload)
            second = record_quality_evidence(payload)

            self.assertEqual(first.id, second.id)

        self.assertEqual(QualityEvidence.objects.count(), len(QualityEvidence.CHECK_CHOICES))
        self.assertEqual(AutoIssue.objects.count(), len(QualityEvidence.CHECK_CHOICES))

    def test_rejects_summary_over_six_hundred_words(self) -> None:
        too_long = "word " * 601

        with self.assertRaisesMessage(ValueError, "600-word"):
            record_quality_evidence(_payload(summary=too_long))

    def test_raw_snippet_is_deduped_by_hash(self) -> None:
        payload = _payload(
            raw_report_text="same raw report",
            capture_raw_snippet=True,
        )

        first = record_quality_evidence(payload)
        second = record_quality_evidence(payload)

        self.assertEqual(first.raw_snippet_id, second.raw_snippet_id)
        snippet = QualityRawSnippet.objects.get(pk=first.raw_snippet_id)
        self.assertEqual(snippet.reference_count, 2)

    def test_new_failed_raw_snippet_is_saved_before_weekly_window(self) -> None:
        evidence = record_quality_evidence(
            _payload(
                raw_report_text="new failure output",
                capture_raw_snippet=False,
            )
        )

        self.assertIsNotNone(evidence.raw_snippet)
        self.assertEqual(QualityRawSnippet.objects.count(), 1)

    def test_repeated_raw_snippet_reuses_existing_content_hash(self) -> None:
        first = record_quality_evidence(
            _payload(raw_report_text="same failure output", source_hash="one")
        )
        second = record_quality_evidence(
            _payload(raw_report_text="same failure output", source_hash="two")
        )

        self.assertEqual(first.raw_snippet_id, second.raw_snippet_id)
        snippet = QualityRawSnippet.objects.get(pk=first.raw_snippet_id)
        self.assertEqual(snippet.reference_count, 2)

    def test_weekly_capture_is_due_inside_window_once_per_week(self) -> None:
        london = ZoneInfo("Europe/London")
        inside_window = datetime.combine(
            date(2026, 5, 18),
            time(12, 0),
            tzinfo=london,
        )

        self.assertTrue(should_capture_weekly_raw_snippet(now=inside_window))
        QualityRawSnippet.objects.create(
            raw_report_hash="d" * 64,
            raw_report_gzip=b"raw",
            uncompressed_bytes=3,
            compressed_bytes=3,
            first_captured_week_start=date(2026, 5, 18),
            last_captured_week_start=date(2026, 5, 18),
        )

        self.assertFalse(should_capture_weekly_raw_snippet(now=inside_window))

    def test_first_weekly_capture_waits_for_window(self) -> None:
        monday_before_window = datetime.combine(
            date(2026, 5, 18),
            time(8, 0),
            tzinfo=ZoneInfo("Europe/London"),
        )
        monday_after_window = datetime.combine(
            date(2026, 5, 18),
            time(23, 30),
            tzinfo=ZoneInfo("Europe/London"),
        )

        self.assertFalse(should_capture_weekly_raw_snippet(now=monday_before_window))
        self.assertTrue(should_capture_weekly_raw_snippet(now=monday_after_window))

    def test_previous_week_miss_catches_up_before_window(self) -> None:
        monday_before_window = datetime.combine(
            date(2026, 5, 25),
            time(8, 0),
            tzinfo=ZoneInfo("Europe/London"),
        )
        old_week = date(2026, 5, 4)
        QualityRawSnippet.objects.create(
            raw_report_hash="a" * 64,
            raw_report_gzip=b"raw",
            uncompressed_bytes=3,
            compressed_bytes=3,
            first_captured_week_start=old_week,
            last_captured_week_start=old_week,
        )

        self.assertTrue(should_capture_weekly_raw_snippet(now=monday_before_window))

    def test_previous_week_capture_waits_until_window(self) -> None:
        monday_before_window = datetime.combine(
            date(2026, 5, 25),
            time(8, 0),
            tzinfo=ZoneInfo("Europe/London"),
        )
        previous_week = date(2026, 5, 18)
        QualityRawSnippet.objects.create(
            raw_report_hash="b" * 64,
            raw_report_gzip=b"raw",
            uncompressed_bytes=3,
            compressed_bytes=3,
            first_captured_week_start=previous_week,
            last_captured_week_start=previous_week,
        )

        self.assertFalse(should_capture_weekly_raw_snippet(now=monday_before_window))

    def test_prune_old_raw_snippets_keeps_active_references(self) -> None:
        now = timezone.now()
        old_week = timezone.localdate() - timedelta(weeks=20)
        old_snippet = QualityRawSnippet.objects.create(
            raw_report_hash="c" * 64,
            raw_report_gzip=b"raw",
            uncompressed_bytes=3,
            compressed_bytes=3,
            first_captured_week_start=old_week,
            last_captured_week_start=old_week,
        )
        evidence = record_quality_evidence(_payload(raw_report_text=""))
        evidence.raw_snippet = old_snippet
        evidence.expires_at = now + timedelta(days=1)
        evidence.save(update_fields=["raw_snippet", "expires_at"])

        pruned = prune_old_raw_snippets(now=now, keep_weeks=0)

        self.assertEqual(pruned, 0)
        self.assertTrue(QualityRawSnippet.objects.filter(pk=old_snippet.pk).exists())

    def test_ingest_command_imports_json_lines_evidence(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            path = Path(handle.name)
            handle.write(
                json.dumps(
                    {
                        "check_type": QualityEvidence.CHECK_TOOL_READINESS,
                        "status": QualityEvidence.STATUS_PASSED,
                        "tool_name": "docker",
                        "command": "docker compose run --rm backend true",
                        "summary": "Tool readiness passed for the backend container.",
                    }
                )
            )

        try:
            output = StringIO()
            call_command("ingest_quality_evidence", path=path, stdout=output)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(QualityEvidence.objects.filter(tool_name="docker").count(), 1)
        self.assertIn("QUALITY EVIDENCE IMPORTED: 1", output.getvalue())


class QualityArtifactTests(SimpleTestCase):
    def test_finds_only_known_quality_temp_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mutmut-backend-123").mkdir()
            (root / "coverage-backend-run").mkdir()
            (root / "media_files").mkdir()

            found = {path.name for path in find_quality_artifacts(root)}

        self.assertEqual(found, {"coverage-backend-run", "mutmut-backend-123"})

    def test_prune_dry_run_does_not_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "pytest-debug-123"
            artifact.mkdir()
            (artifact / "result.txt").write_text("failed test", encoding="utf-8")

            results = prune_quality_artifacts(root=root, dry_run=True)

            self.assertEqual(len(results), 1)
            self.assertTrue(artifact.exists())

    def test_refuses_protected_volume_root(self) -> None:
        with self.assertRaisesMessage(ValueError, "protected data store"):
            find_quality_artifacts(Path("/tmp/pgdata"))


class ProtectedDataMapTests(SimpleTestCase):
    def test_all_compose_volumes_are_protected(self) -> None:
        repo_root = Path(os.environ.get("REPO_ROOT", Path(settings.BASE_DIR).parent))
        protected = json.loads(
            (repo_root / "config" / "protected-data-stores.json").read_text(
                encoding="utf-8"
            )
        )
        compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
        compose_volumes = _compose_volume_names(compose_text)

        self.assertTrue(compose_volumes.issubset(set(protected["docker_volumes"])))


def _compose_volume_names(compose_text: str) -> set[str]:
    names: set[str] = set()
    in_block = False
    for line in compose_text.splitlines():
        if line == "volumes:":
            in_block = True
            continue
        if in_block and line and not line.startswith(" "):
            break
        if in_block:
            match = re.match(r"\s{2}([A-Za-z0-9_.-]+):\s*$", line)
            if match:
                names.add(match.group(1))
    return names
