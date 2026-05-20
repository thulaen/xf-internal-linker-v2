# FR: Audit HTTP Lookup With SQLite Cache

[SPEC FRESHNESS: reviewed_at=2026-05-20 next_review=2026-06-20]
[SPEC CITED: feature=audit-http-lookup-sqlite kind=technical_doc id=https://www.sqlite.org/wal.html verified_at=2026-05-20T01:15:00Z]
[SPEC CITED: feature=audit-http-lookup-sqlite kind=technical_doc id=https://docs.python.org/3/library/sqlite3.html verified_at=2026-05-20T01:15:00Z]
[SPEC CITED: feature=audit-http-lookup-sqlite kind=technical_doc id=https://docs.djangoproject.com/en/5.2/ref/request-response/ verified_at=2026-05-20T01:15:00Z]
[SPEC CITED: SQLite WAL documentation=https://www.sqlite.org/wal.html source_type=technical_doc reviewed_at=2026-05-20]
[SPEC CITED: Python sqlite3 documentation=https://docs.python.org/3/library/sqlite3.html source_type=technical_doc reviewed_at=2026-05-20]
[SPEC CITED: Django response documentation=https://docs.djangoproject.com/en/5.2/ref/request-response/ source_type=technical_doc reviewed_at=2026-05-20]

## Purpose

Per-file resolved-issue lookups currently read the JSONL index directly. That is safe offline, but it is slower than needed when the backend container is already running. This slice adds a SQLite index and a localhost-only HTTP lookup endpoint. Redis is intentionally out of scope for this first version.

## Behavior

Given `audit/resolved_issues_index.jsonl` exists, when `manage.py migrate_audit_to_sqlite` runs, then `audit/resolved_issues_index.sqlite` is created with WAL mode enabled, an `entries` table keyed by normalized `file_path`, and a `lookup_log` table that records every lookup.

Given the backend is running, when `scripts/lookup_remote_or_local.py --area <path>` is called, then it posts the file paths to `/api/internal/audit/lookup/` and prints the same `[RESOLVED SEARCH: ...]` lines as the disk helper.

Given the backend is down or returns a non-success response, when the remote-or-local helper runs, then it executes `scripts/lookup_disk_index.py` with the original arguments.

Given the JSONL source file changes after the SQLite file was built, when the next HTTP lookup runs, then the service notices the newer source mtime and rebuilds the SQLite index before answering.

## Budgets

- Warm lookup target: under 50 ms when the SQLite page cache is warm.
- Cold lookup target: under 200 ms for the first lookup after a backend restart.
- Stale data target: the next request after a JSONL mtime change sees the refreshed rows.

## Non-Goals

- No Redis shared cache in this first commit.
- No generated SQLite database file is committed to Git.
- No broad rewrite of the existing disk helper.
