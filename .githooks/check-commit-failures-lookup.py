#!/usr/bin/env python3
"""Pre-commit gate: agents must look up prior commit failures before committing.

USER RULE (2026-05-18):
  Agents should also look up commit failures before committing, just like
  they look up resolved issues when editing code. The lookup must produce
  evidence on disk that it was run for the current task.

This hook implements the hard-block: the chain refuses any code-changing
commit that has no record of a `manage.py search_commit_failures` call in
the disk-backed audit log `audit/commit_failures_lookup_log.jsonl` under
the current task_id.

The lookup is task-scoped (not per-file). The agent runs the search ONCE
per task — typically right after `preflight_tdd` and the per-file resolved
lookups — and that satisfies the gate. Re-runs are fine but not required.

Source: docs/PER-FILE-LESSON-LOOKUP-RULE.md (authored 2026-05-18) and the
2026-05-18 user directive: "agents should also lookup commit failures
before committing".

Rule-F compliant: every FAIL message has WHAT failed / WHY / UNBLOCK.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG_PATH = REPO_ROOT / "audit" / "commit_failures_lookup_log.jsonl"
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


def _current_task_id() -> str:
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


def _lookup_count_for_task(task_id: str) -> int:
    if not AUDIT_LOG_PATH.exists():
        return 0
    count = 0
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
                    count += 1
    except OSError:
        return 0
    return count


def main() -> int:
    files = _staged_production_files()
    if not files:
        return 0

    task_id = _current_task_id()
    count = _lookup_count_for_task(task_id)

    if count == 0:
        sys.stderr.write(
            f"FAIL check-commit-failures-lookup: zero commit-failure lookups "
            f"recorded for task_id={task_id} in "
            f"{AUDIT_LOG_PATH.relative_to(REPO_ROOT)}.\n"
            "WHY: the 2026-05-18 user rule requires every agent to look up "
            "prior commit failures BEFORE committing, parallel to the "
            "per-file search_resolved_issues mandate. Without the lookup, "
            "the agent risks repeating a failure (timeout, orphan DB "
            "connection, missing marker, etc.) that an earlier session "
            "already diagnosed. A memory-only lookup does NOT satisfy the "
            "mandate; the audit log is the disk-backed evidence.\n"
            "UNBLOCK: run `docker compose exec -T backend python manage.py "
            "search_commit_failures` once at session start (re-runs are "
            "fine but not required). The command writes one entry per call "
            "to audit/commit_failures_lookup_log.jsonl with the current "
            "task_id automatically captured from the [TDD PREFLIGHT: ...] "
            "marker. Then re-run the commit.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
