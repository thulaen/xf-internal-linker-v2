"""Append-only GitHub Actions failure history helpers."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Iterable

from django.utils import timezone
from django.utils.dateparse import parse_datetime

REPO_ROOT = Path("/repo") if Path("/repo").exists() else Path(__file__).resolve().parents[4]
HISTORY_PATH = REPO_ROOT / "audit" / "github_actions_failures.jsonl"
PICK_LIMIT = 3


def append_history(entry: dict[str, Any], path: Path | None = None) -> None:
    """Append one JSON object to the history log using append mode."""
    target = path or HISTORY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(entry, sort_keys=True) + "\n"
    fd = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)


def read_history(path: Path | None = None) -> Iterable[dict[str, Any]]:
    """Yield valid JSON objects from the history log."""
    target = path or HISTORY_PATH
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def open_failures_since(since: datetime | None, path: Path | None = None) -> list[dict[str, Any]]:
    """Return open failures newer than the given timestamp."""
    rows = [row for row in read_history(path) if _is_open_failure_after(row, since)]
    return sorted(rows, key=lambda row: _parse_time(row.get("failed_at")), reverse=True)


def since_handoff_marker(since: datetime | None, path: Path | None = None) -> str:
    """Return the exact session-start marker for recent failures."""
    rows = open_failures_since(since, path)
    picks = _picked_runs(rows)
    return f"[GH ACTIONS READ: {len(rows)} failures since last handoff — picked: {picks}]"


def trend_rows(path: Path | None = None, *, top: int = 5) -> list[dict[str, Any]]:
    """Group failures by workflow and job name."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in read_history(path):
        for job in row.get("failing_jobs") or []:
            key = (str(row.get("workflow") or "unknown"), str(job.get("name") or "unknown"))
            group = groups.setdefault(key, _new_group(key))
            _add_trend_row(group, row)
    ordered = sorted(groups.values(), key=lambda row: (-row["count"], row["last_failed_at"]))
    return ordered[:top]


def append_resolution_history(issue, path: Path | None = None) -> None:
    """Append resolved lines for a resolved GitHub Actions AutoIssue."""
    if issue.source != issue.SOURCE_GH_CI or issue.status != issue.STATUS_RESOLVED:
        return
    resolved_at = issue.resolved_at or timezone.now()
    for run_id in _run_ids(issue.source_observations or []):
        append_history(
            {
                "run_id": run_id,
                "status": "resolved",
                "resolved_at": resolved_at.isoformat(),
                "resolved_by_autoissue_id": issue.pk,
            },
            path,
        )


def rotate_before(cutoff: datetime, path: Path | None = None) -> tuple[int, int]:
    """Move entries older than cutoff into yearly archive files."""
    target = path or HISTORY_PATH
    moved: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for row in read_history(target):
        if _parse_time(row.get("failed_at")) < cutoff:
            moved.append(row)
        else:
            kept.append(row)
    _write_active(target, kept)
    for year, entries in _by_year(moved).items():
        archive = target.with_name(f"github_actions_failures.archive.{year}.jsonl")
        for entry in entries:
            append_history(entry, archive)
    return len(moved), len(kept)


def _is_open_failure_after(row: dict[str, Any], since: datetime | None) -> bool:
    if row.get("status") != "open":
        return False
    return since is None or _parse_time(row.get("failed_at")) > since


def _parse_time(value: object) -> datetime:
    parsed = parse_datetime(str(value or "")) or datetime.min.replace(tzinfo=dt_timezone.utc)
    if parsed.tzinfo is None:
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _picked_runs(rows: list[dict[str, Any]]) -> str:
    picked = [f"#{row.get('run_id')}" for row in rows[:PICK_LIMIT]]
    return ", ".join(picked) if picked else "none"


def _new_group(key: tuple[str, str]) -> dict[str, Any]:
    workflow, job = key
    return {
        "workflow": workflow,
        "job": job,
        "count": 0,
        "last_failed_at": "",
        "sample_run_url": "",
        "open_autoissue_count": 0,
    }


def _add_trend_row(group: dict[str, Any], row: dict[str, Any]) -> None:
    group["count"] += 1
    failed_at = str(row.get("failed_at") or "")
    if failed_at > group["last_failed_at"]:
        group["last_failed_at"] = failed_at
        group["sample_run_url"] = str(row.get("run_url") or "")
    if row.get("status") == "open":
        group["open_autoissue_count"] += len(row.get("autoissue_ids") or [])


def _run_ids(observations: Iterable[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for observation in observations:
        run_id = str(observation.get("run_id") or "").strip()
        if run_id and run_id not in seen:
            seen.add(run_id)
            ids.append(run_id)
    return ids


def _write_active(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    tmp.replace(path)


def _by_year(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_parse_time(row.get("failed_at")).year].append(row)
    return grouped
