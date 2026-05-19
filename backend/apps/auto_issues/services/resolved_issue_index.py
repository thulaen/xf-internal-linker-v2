"""Disk-backed resolved-issue index + audit log for the per-file mandate.

The 2026-05-18 user rule requires every staged file to have had
`manage.py search_resolved_issues` run for its exact path before the first
modification in the current agent task. This module is the durable layer:

  - `audit/resolved_issues_index.jsonl`        — source of truth on disk
  - `audit/resolved_issues_lookup_log.jsonl`   — append-only audit log

A RAM cache (module-level dict) speeds up repeat lookups within a process,
but the cache is populated from the disk-backed index. A memory-only lookup
does not satisfy the mandate; every lookup must append a record to the audit
log.

Source: docs/PER-FILE-LESSON-LOOKUP-RULE.md (authored 2026-05-18; user
directive: "if all these rules are not met commit should hard block").
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

def _detect_repo_root() -> Path:
    """Detect the repo root regardless of whether we run inside docker.

    Inside the backend container the source tree is mounted at /repo while
    Python sees this file at /app/apps/...; on the host or in tests the file
    sits at <repo>/backend/apps/... and ancestry resolution works.
    """
    container_root = Path("/repo")
    if container_root.exists() and (container_root / "AGENT-HANDOFF.md").exists():
        return container_root
    return Path(__file__).resolve().parents[4]


REPO_ROOT = _detect_repo_root()
AUDIT_DIR = REPO_ROOT / "audit"
INDEX_PATH = AUDIT_DIR / "resolved_issues_index.jsonl"
AUDIT_LOG_PATH = AUDIT_DIR / "resolved_issues_lookup_log.jsonl"
HANDOFF_PATH = REPO_ROOT / "AGENT-HANDOFF.md"

# The 11 required fields per the user-defined contract.
REQUIRED_FIELDS = (
    "file_path",
    "issue_title",
    "date_resolved",
    "root_cause",
    "what_failed",
    "what_fixed_it",
    "regression_risk",
    "tests_added_or_changed",
    "related_files",
    "patterns_to_avoid",
    "safe_implementation_notes",
)

_PREFLIGHT_SESSION_RE = re.compile(
    r"\[TDD PREFLIGHT:[^\]]*session_id=(?P<sid>[0-9a-f-]{8,})", re.IGNORECASE
)

_cache_lock = threading.Lock()
_index_cache: dict[str, list[dict[str, Any]]] | None = None
_index_cache_path_mtime: float | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_audit_dir() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _normalise_path(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("/")


def load_index(force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Return the index as a dict keyed by file_path. Lazy + cached."""
    global _index_cache, _index_cache_path_mtime
    with _cache_lock:
        if not INDEX_PATH.exists():
            _index_cache = {}
            _index_cache_path_mtime = None
            return _index_cache

        current_mtime = INDEX_PATH.stat().st_mtime
        if (
            not force_refresh
            and _index_cache is not None
            and _index_cache_path_mtime == current_mtime
        ):
            return _index_cache

        cache: dict[str, list[dict[str, Any]]] = {}
        with INDEX_PATH.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed line; the export command should be re-run.
                    continue
                file_path = _normalise_path(entry.get("file_path", ""))
                if not file_path:
                    continue
                cache.setdefault(file_path, []).append(entry)

        _index_cache = cache
        _index_cache_path_mtime = current_mtime
        return _index_cache


def write_index(entries: Iterable[dict[str, Any]]) -> int:
    """Overwrite the JSONL index with the given iterable; return count."""
    _ensure_audit_dir()
    count = 0
    tmp = INDEX_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for entry in entries:
            line = json.dumps(_serialise_entry(entry), ensure_ascii=False)
            fh.write(line + "\n")
            count += 1
    os.replace(tmp, INDEX_PATH)
    # Invalidate the RAM cache after a write.
    with _cache_lock:
        global _index_cache, _index_cache_path_mtime
        _index_cache = None
        _index_cache_path_mtime = None
    return count


def _serialise_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalise an entry: required fields present, lists are lists, strings stripped."""
    out: dict[str, Any] = {}
    for field in REQUIRED_FIELDS:
        value = entry.get(field, "")
        if field in {"tests_added_or_changed", "related_files", "patterns_to_avoid"}:
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            elif value is None:
                value = []
            else:
                value = [str(v).strip() for v in value if str(v).strip()]
        elif value is None:
            value = ""
        else:
            value = str(value).strip()
        out[field] = value
    # Optional carry-through fields.
    for extra in ("autoissue_id", "source", "category", "concept_tags"):
        if extra in entry:
            out[extra] = entry[extra]
    return out


def lookup(path: str) -> list[dict[str, Any]]:
    """Return all index entries whose file_path matches the supplied path."""
    cache = load_index()
    normalised = _normalise_path(path)
    return list(cache.get(normalised, []))


def _staged_handoff_text() -> str:
    """Return the working-tree AGENT-HANDOFF.md head plus any staged diff."""
    try:
        if HANDOFF_PATH.exists():
            return HANDOFF_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return ""


def current_task_id() -> str:
    """Return the canonical task_id for the current session.

    Strategy:
      1. Latest [TDD PREFLIGHT: ... session_id=<uuid> ...] in AGENT-HANDOFF.md.
      2. SHA of (git HEAD + current day in ISO 8601 UTC) as a deterministic
         fallback so the audit log is still keyed consistently across the
         day even without a preflight marker.
    """
    text = _staged_handoff_text()
    if text:
        match = _PREFLIGHT_SESSION_RE.search(text)
        if match:
            return match.group("sid")

    # Fallback: SHA of git HEAD + today's UTC date.
    try:
        # Fixed git command; no user input reaches subprocess.
        head = subprocess.run(  # nosec
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip() or "no-head"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        head = "no-head"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"fallback-{head[:12]}-{today}"


def append_audit_entry(
    *,
    file_path: str,
    task_id: str,
    agent: str,
    result_count: int,
    result_ids: list[int],
) -> dict[str, Any]:
    """Append one row to the audit log; return the row that was written."""
    _ensure_audit_dir()
    entry = {
        "file_path": _normalise_path(file_path),
        "lookup_at": _now_iso(),
        "task_id": task_id,
        "agent": agent,
        "result_count": int(result_count),
        "result_ids": list(result_ids),
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def audit_entries_for_task(task_id: str) -> list[dict[str, Any]]:
    """Return all audit log entries written under the supplied task_id."""
    if not AUDIT_LOG_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("task_id") == task_id:
                entries.append(entry)
    return entries


def files_with_lookup_in_task(task_id: str) -> set[str]:
    """Return the set of file paths that have at least one audit entry."""
    return {
        _normalise_path(e.get("file_path", ""))
        for e in audit_entries_for_task(task_id)
        if e.get("file_path")
    }
