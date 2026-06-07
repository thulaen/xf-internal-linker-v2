#!/usr/bin/env python3
"""Pre-commit warning: every staged file should have a disk-backed
search_resolved_issues lookup recorded in the current task.

USER RULE (2026-05-18):
  Before modifying any file, the agent (claude / codex / gemini) MUST run
  search_resolved_issues for that EXACT file path. The lookup is required
  ONCE per file before the first modification to that file in the current
  agent task. The lookup must produce evidence on disk that it was run.
  A memory-only lookup does NOT satisfy the mandate.

This hook implements the warning:

  1. Reads `audit/resolved_issues_lookup_log.jsonl` (the disk-backed audit
     log written by `manage.py search_resolved_issues`).
  2. Determines the current task_id from the [TDD PREFLIGHT: ...
     session_id=<uuid>] marker in the staged AGENT-HANDOFF.md (or falls
     back to a deterministic SHA of git HEAD + today's UTC date).
  3. Collects every file_path that has an audit entry under the current
     task_id.
  4. Compares against the set of staged production source file paths.
  5. Warns if any staged file is missing an audit entry.

The Postgres `pgdata` volume remains the primary source for resolved-issue
content (via AutoIssue.lessons_learned); the JSONL audit log is the
disk-backed evidence that the lookup happened, surviving any database wipe.

Rule-F compliant: every WARN message has WHAT failed / WHY / UNBLOCK.

Source: docs/PER-FILE-LESSON-LOOKUP-RULE.md (authored 2026-05-18).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG_PATH = REPO_ROOT / "audit" / "resolved_issues_lookup_log.jsonl"
HANDOFF_PATH = REPO_ROOT / "AGENT-HANDOFF.md"

_PREFLIGHT_SESSION_RE = re.compile(
    r"\[TDD PREFLIGHT:[^\]]*session_id=(?P<sid>[0-9a-f-]{8,})", re.IGNORECASE
)
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "services/",
)
_NON_SOURCE_PATHS = (
    "AGENT-HANDOFF.md",
    "AI-CONTEXT.md",
    "docs/",
)


def _git_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def _staged_production_files() -> list[str]:
    out = _git_output(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    files: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in _NON_SOURCE_PATHS):
            continue
        if any(line.startswith(p) for p in _CODE_PREFIXES):
            files.append(line)
    return files


def _normalise_path(path: str) -> str:
    return str(path).replace("\\", "/").strip().strip("/")


def _current_task_id() -> str:
    """Mirror apps.auto_issues.services.resolved_issue_index.current_task_id."""
    text = ""
    if HANDOFF_PATH.exists():
        try:
            text = HANDOFF_PATH.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    if text:
        match = _PREFLIGHT_SESSION_RE.search(text)
        if match:
            return match.group("sid")
    head = _git_output(["rev-parse", "HEAD"]).strip() or "no-head"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"fallback-{head[:12]}-{today}"


def _audit_entries_for_task(task_id: str) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    entries: list[dict] = []
    try:
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
    except OSError:
        return []
    return entries


def _warn(message: str) -> int:
    sys.stderr.write(message)
    return 0


def main() -> int:
    files = _staged_production_files()
    if not files:
        return 0

    task_id = _current_task_id()
    audit_entries = _audit_entries_for_task(task_id)

    if not AUDIT_LOG_PATH.exists():
        return _warn(
            "WARN check-resolved-history: disk-backed audit log "
            f"{AUDIT_LOG_PATH.relative_to(REPO_ROOT)} does not exist.\n"
            "WHY: the 2026-05-18 user rule requires every staged file to "
            "have a disk-backed search_resolved_issues lookup recorded for "
            "the current task. The audit log is the source of truth for "
            "that evidence; without it the hook cannot prove any lookup "
            "happened. A memory-only lookup does NOT satisfy the mandate.\n"
            "UNBLOCK: for each staged production source file, run "
            "`docker compose exec -T backend python manage.py "
            "search_resolved_issues --area <exact file path>`. Each call "
            "appends one entry to audit/resolved_issues_lookup_log.jsonl. "
            "Re-run the commit once every staged file has an entry.\n"
        )

    if not audit_entries:
        return _warn(
            f"WARN check-resolved-history: zero audit log entries for "
            f"task_id={task_id}.\n"
            f"WHY: the 2026-05-18 user rule requires every staged file to "
            f"have a disk-backed search_resolved_issues lookup recorded for "
            f"the current task. No lookup has been recorded for this task "
            f"yet.\n"
            "UNBLOCK: for each staged production source file, run "
            "`docker compose exec -T backend python manage.py "
            "search_resolved_issues --area <exact file path>`. The "
            "command writes one entry per --area call to "
            "audit/resolved_issues_lookup_log.jsonl with the current "
            "task_id automatically captured from the [TDD PREFLIGHT: "
            "...] marker.\n"
        )

    covered: set[str] = {
        _normalise_path(e.get("file_path", "")) for e in audit_entries
    }
    covered.discard("")

    uncovered = [p for p in files if _normalise_path(p) not in covered]

    if uncovered:
        listed = "\n".join(f"  staged (no audit entry): {p}" for p in uncovered[:8])
        more = (
            f"\n  ... and {len(uncovered) - 8} more"
            if len(uncovered) > 8
            else ""
        )
        return _warn(
            f"WARN check-resolved-history: {len(uncovered)} staged "
            f"production source file(s) have NO disk-backed "
            f"search_resolved_issues audit entry under task_id={task_id}.\n"
            f"{listed}{more}\n"
            f"  audit entries this task: {len(audit_entries)} covering "
            f"{len(covered)} unique file path(s).\n"
            "WHY: the 2026-05-18 user rule requires the lookup to be done "
            "for the EXACT file path of every file modified in the current "
            "agent task. The lookup result must be persisted to "
            "audit/resolved_issues_lookup_log.jsonl as durable evidence "
            "(memory-only lookup does NOT count).\n"
            "UNBLOCK: for each unlisted file above, run "
            "`docker compose exec -T backend python manage.py "
            "search_resolved_issues --area <exact file path>`. After every "
            "missing file is covered, re-run the commit.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
