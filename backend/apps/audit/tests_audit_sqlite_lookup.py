import json
import sqlite3
from pathlib import Path

from django.core.management import call_command
from rest_framework.test import APIRequestFactory

from apps.audit.services.audit_lookup import (
    lookup_resolved_issues,
    migrate_jsonl_to_sqlite,
)
from apps.audit.views import InternalAuditLookupView


def _append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload) + "\n")


def test_migrates_jsonl_to_sqlite_and_logs_lookup(tmp_path):
    jsonl_path = tmp_path / "resolved_issues_index.jsonl"
    sqlite_path = tmp_path / "resolved_issues_index.sqlite"
    _append_jsonl(
        jsonl_path,
        {
            "file_path": "scripts/lookup_disk_index.py",
            "autoissue_id": 42,
            "issue_title": "lookup stayed fast",
        },
    )

    migrate_jsonl_to_sqlite(jsonl_path=jsonl_path, sqlite_path=sqlite_path)
    result = lookup_resolved_issues(
        sqlite_path=sqlite_path,
        jsonl_path=jsonl_path,
        file_paths=["scripts/lookup_disk_index.py"],
        task_id="task-1",
        agent="codex",
    )

    assert result["paths"]["scripts/lookup_disk_index.py"]["result_count"] == 1
    assert result["paths"]["scripts/lookup_disk_index.py"]["matches"][0]["autoissue_id"] == 42
    with sqlite3.connect(sqlite_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        rows = conn.execute(
            "SELECT task_id, file_path, result_count, result_ids FROM lookup_log"
        ).fetchall()
    assert rows == [("task-1", "scripts/lookup_disk_index.py", 1, "[42]")]


def test_migrate_audit_to_sqlite_command_writes_sqlite_file(tmp_path):
    jsonl_path = tmp_path / "resolved_issues_index.jsonl"
    sqlite_path = tmp_path / "resolved_issues_index.sqlite"
    _append_jsonl(
        jsonl_path,
        {"file_path": "backend/apps/audit/views.py", "autoissue_id": 64},
    )

    call_command(
        "migrate_audit_to_sqlite",
        jsonl=str(jsonl_path),
        sqlite=str(sqlite_path),
    )

    with sqlite3.connect(sqlite_path) as conn:
        payload = conn.execute(
            "SELECT payload FROM entries WHERE file_path = ?",
            ("backend/apps/audit/views.py",),
        ).fetchone()[0]
    assert json.loads(payload)[0]["autoissue_id"] == 64


def test_lookup_refreshes_when_jsonl_mtime_changes(tmp_path):
    jsonl_path = tmp_path / "resolved_issues_index.jsonl"
    sqlite_path = tmp_path / "resolved_issues_index.sqlite"
    _append_jsonl(
        jsonl_path,
        {"file_path": "backend/apps/audit/views.py", "autoissue_id": 11},
    )
    migrate_jsonl_to_sqlite(jsonl_path=jsonl_path, sqlite_path=sqlite_path)

    _append_jsonl(
        jsonl_path,
        {"file_path": "backend/apps/audit/views.py", "autoissue_id": 12},
    )
    result = lookup_resolved_issues(
        sqlite_path=sqlite_path,
        jsonl_path=jsonl_path,
        file_paths=["backend/apps/audit/views.py"],
        task_id="task-2",
        agent="codex",
    )

    assert result["paths"]["backend/apps/audit/views.py"]["result_count"] == 2
    assert result["paths"]["backend/apps/audit/views.py"]["result_ids"] == [11, 12]


def test_internal_lookup_endpoint_rejects_non_local_requests(tmp_path, settings):
    settings.AUDIT_SQLITE_INDEX_PATH = str(tmp_path / "resolved_issues_index.sqlite")
    settings.AUDIT_RESOLVED_ISSUES_INDEX_PATH = str(
        tmp_path / "resolved_issues_index.jsonl"
    )
    settings.AUDIT_RESOLVED_ISSUES_LOOKUP_LOG_PATH = str(tmp_path / "lookup.jsonl")
    Path(settings.AUDIT_RESOLVED_ISSUES_INDEX_PATH).write_text(
        json.dumps({"file_path": "scripts/lookup_disk_index.py", "autoissue_id": 9})
        + "\n",
        encoding="utf-8",
    )
    request = APIRequestFactory().post(
        "/api/internal/audit/lookup",
        {"file_paths": ["scripts/lookup_disk_index.py"], "task_id": "task-3"},
        format="json",
        REMOTE_ADDR="203.0.113.10",
    )

    response = InternalAuditLookupView.as_view()(request)

    assert response.status_code == 403


def test_internal_lookup_endpoint_returns_sqlite_results_for_local_bridge(
    tmp_path, settings
):
    settings.AUDIT_SQLITE_INDEX_PATH = str(tmp_path / "resolved_issues_index.sqlite")
    settings.AUDIT_RESOLVED_ISSUES_INDEX_PATH = str(
        tmp_path / "resolved_issues_index.jsonl"
    )
    settings.AUDIT_RESOLVED_ISSUES_LOOKUP_LOG_PATH = str(tmp_path / "lookup.jsonl")
    Path(settings.AUDIT_RESOLVED_ISSUES_INDEX_PATH).write_text(
        json.dumps(
            {
                "file_path": "backend/apps/audit/services/audit_lookup.py",
                "autoissue_id": 77,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = APIRequestFactory().post(
        "/api/internal/audit/lookup",
        {
            "file_paths": ["backend/apps/audit/services/audit_lookup.py"],
            "task_id": "task-4",
            "agent": "codex",
        },
        format="json",
        REMOTE_ADDR="172.19.0.1",
    )

    response = InternalAuditLookupView.as_view()(request)

    assert response.status_code == 200
    assert (
        response.data["paths"]["backend/apps/audit/services/audit_lookup.py"][
            "result_ids"
        ]
        == [77]
    )
    lookup_log = Path(settings.AUDIT_RESOLVED_ISSUES_LOOKUP_LOG_PATH).read_text(
        encoding="utf-8"
    )
    assert '"task_id": "task-4"' in lookup_log
