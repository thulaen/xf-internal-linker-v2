"""SQLite-backed resolved-issue lookup for commit hooks."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

def _detect_repo_root() -> Path:
    configured = os.environ.get("REPO_ROOT")
    if configured:
        return Path(configured)
    container_root = Path("/repo")
    if container_root.exists() and (container_root / "AGENT-HANDOFF.md").exists():
        return container_root
    return Path(__file__).resolve().parents[4]


DEFAULT_REPO_ROOT = _detect_repo_root()
DEFAULT_JSONL_PATH = DEFAULT_REPO_ROOT / "audit" / "resolved_issues_index.jsonl"
DEFAULT_SQLITE_PATH = DEFAULT_REPO_ROOT / "audit" / "resolved_issues_index.sqlite"
DEFAULT_AUDIT_LOG_PATH = DEFAULT_REPO_ROOT / "audit" / "resolved_issues_lookup_log.jsonl"


def normalise_path(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("/")


def migrate_jsonl_to_sqlite(*, jsonl_path: Path, sqlite_path: Path) -> int:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    grouped = _read_jsonl_grouped(jsonl_path)
    with _connect(sqlite_path) as conn:
        _create_schema(conn)
        conn.execute("DELETE FROM entries")
        conn.execute("DELETE FROM metadata WHERE key = 'source_mtime_ns'")
        for file_path, rows in sorted(grouped.items()):
            conn.execute(
                "INSERT INTO entries(file_path, payload) VALUES (?, ?)",
                (file_path, json.dumps(rows, separators=(",", ":"))),
            )
        source_mtime = _mtime_ns(jsonl_path)
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES ('source_mtime_ns', ?)",
            (str(source_mtime),),
        )
    return sum(len(rows) for rows in grouped.values())


def lookup_resolved_issues(
    *,
    sqlite_path: Path,
    jsonl_path: Path,
    file_paths: list[str],
    task_id: str,
    agent: str,
    legacy_audit_log_path: Path | None = None,
) -> dict[str, Any]:
    _ensure_fresh(sqlite_path=sqlite_path, jsonl_path=jsonl_path)
    normalized = [normalise_path(path) for path in file_paths]
    started = time.perf_counter()
    paths: dict[str, dict[str, Any]] = {}
    with _connect(sqlite_path) as conn:
        _create_schema(conn)
        for file_path in normalized:
            rows = _fetch_rows(conn, file_path)
            ids = _result_ids(rows)
            paths[file_path] = {
                "result_count": len(rows),
                "result_ids": ids,
                "matches": rows,
            }
            conn.execute(
                """
                INSERT INTO lookup_log(ts, task_id, agent, file_path, result_count, result_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    task_id,
                    agent,
                    file_path,
                    len(rows),
                    json.dumps(ids, separators=(",", ":")),
                ),
            )
            if legacy_audit_log_path is not None:
                _append_legacy_audit_log(
                    audit_log_path=legacy_audit_log_path,
                    file_path=file_path,
                    task_id=task_id,
                    agent=agent,
                    result_count=len(rows),
                    result_ids=ids,
                )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {"source": "sqlite", "elapsed_ms": elapsed_ms, "paths": paths}


def _ensure_fresh(*, sqlite_path: Path, jsonl_path: Path) -> None:
    if not sqlite_path.exists():
        migrate_jsonl_to_sqlite(jsonl_path=jsonl_path, sqlite_path=sqlite_path)
        return
    with _connect(sqlite_path) as conn:
        _create_schema(conn)
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'source_mtime_ns'"
        ).fetchone()
    current_mtime = str(_mtime_ns(jsonl_path))
    if not row or row[0] != current_mtime:
        migrate_jsonl_to_sqlite(jsonl_path=jsonl_path, sqlite_path=sqlite_path)


def _connect(sqlite_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=1000")
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            file_path TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lookup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            file_path TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            result_ids TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS lookup_log_task_idx ON lookup_log(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS lookup_log_file_idx ON lookup_log(file_path)")


def _read_jsonl_grouped(jsonl_path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not jsonl_path.exists():
        return grouped
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            entry = _decode_line(line)
            if not entry:
                continue
            file_path = normalise_path(str(entry.get("file_path", "")))
            if file_path:
                grouped.setdefault(file_path, []).append(entry)
    return grouped


def _decode_line(line: str) -> dict[str, Any] | None:
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    return entry if isinstance(entry, dict) else None


def _fetch_rows(conn: sqlite3.Connection, file_path: str) -> list[dict[str, Any]]:
    row = conn.execute(
        "SELECT payload FROM entries WHERE file_path = ?",
        (file_path,),
    ).fetchone()
    if not row:
        return []
    payload = json.loads(row[0])
    return payload if isinstance(payload, list) else []


def _result_ids(rows: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for row in rows:
        raw_id = row.get("autoissue_id")
        if isinstance(raw_id, int):
            ids.append(raw_id)
    return ids


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _append_legacy_audit_log(
    *,
    audit_log_path: Path,
    file_path: str,
    task_id: str,
    agent: str,
    result_count: int,
    result_ids: list[int],
) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "file_path": normalise_path(file_path),
        "lookup_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_id": task_id,
        "agent": agent,
        "result_count": result_count,
        "result_ids": result_ids,
    }
    with audit_log_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
