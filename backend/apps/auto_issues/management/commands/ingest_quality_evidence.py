"""Import compact quality-check evidence JSON into AutoIssues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services.quality_evidence import (
    QualityEvidenceInput,
    prune_old_raw_snippets,
    record_quality_evidence,
    should_capture_weekly_raw_snippet,
)


class Command(BaseCommand):
    help = "Import one quality evidence JSON file or JSON-lines file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", required=True, type=Path)
        parser.add_argument(
            "--capture-raw-if-due",
            action="store_true",
            help="Attach deduped raw snippets when the weekly capture is due.",
        )

    def handle(self, *args, **options) -> None:
        path: Path = options["path"]
        if not path.is_file():
            raise CommandError(f"Quality evidence file not found: {path}")

        capture_raw = bool(options["capture_raw_if_due"]) and should_capture_weekly_raw_snippet()
        count = 0
        for row in _load_rows(path):
            evidence = record_quality_evidence(_to_payload(row, capture_raw))
            count += 1
            self.stdout.write(f"imported quality evidence #{evidence.id}")
        if capture_raw:
            pruned = prune_old_raw_snippets()
            self.stdout.write(f"QUALITY RAW SNIPPET PRUNED: {pruned}")
        self.stdout.write(f"QUALITY EVIDENCE IMPORTED: {count}")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise CommandError("Quality evidence file must contain an object or list of objects.")


def _to_payload(row: dict[str, Any], capture_raw: bool) -> QualityEvidenceInput:
    return QualityEvidenceInput(
        check_type=str(row["check_type"]),
        status=str(row["status"]),
        tool_name=str(row["tool_name"]),
        command=str(row["command"]),
        summary=str(row["summary"]),
        tool_version=str(row.get("tool_version", "")),
        source_hash=str(row.get("source_hash", "")),
        file_path=str(row.get("file_path", "")),
        failure_fingerprint=str(row.get("failure_fingerprint", "")),
        target_percent=_optional_float(row.get("target_percent")),
        actual_percent=_optional_float(row.get("actual_percent")),
        details=dict(row.get("details") or {}),
        raw_report_text=str(row.get("raw_report_text", "")),
        capture_raw_snippet=capture_raw,
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
