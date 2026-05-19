"""manage.py search_commit_failures — surface prior commit failures and record the lookup.

2026-05-18 user rule: agents should look up commit failures before committing,
parallel to the per-file search_resolved_issues mandate. The lookup is
task-scoped (one call per task is enough). Every call appends one entry to
audit/commit_failures_lookup_log.jsonl so the pre-commit hook
.githooks/check-commit-failures-lookup.py can verify the evidence exists on
disk for the current task_id.

Reads from two sources, in order:
  1. audit/commit_failures_index.jsonl  — disk source of truth (preferred)
  2. AutoIssue rows whose category or title indicates a commit failure
     (fallback when the JSONL index has not been seeded yet)

Output: up to --limit rows summarising each failure with title, date,
root cause (parsed from lessons_learned), and the patterns to avoid.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import resolved_issue_index

INDEX_PATH = resolved_issue_index.REPO_ROOT / "audit" / "commit_failures_index.jsonl"
AUDIT_LOG_PATH = (
    resolved_issue_index.REPO_ROOT / "audit" / "commit_failures_lookup_log.jsonl"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_disk_index() -> list[dict]:
    """Load the disk-backed index file if present; return [] otherwise."""
    if not INDEX_PATH.exists():
        return []
    entries: list[dict] = []
    with INDEX_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _query_db_fallback(limit: int) -> list[dict]:
    """Surface AutoIssue rows whose title or category points at a commit failure."""
    qs = AutoIssue.objects.filter(
        Q(title__icontains="commit")
        | Q(title__icontains="chain")
        | Q(title__icontains="hook failure")
        | Q(category__key__in=("hook_failure", "tooling", "tdd_lesson"))
    ).order_by("-last_seen")[:limit * 4]
    entries: list[dict] = []
    for row in qs:
        body = (row.lessons_learned or "") + (row.description or "")
        if "commit" not in body.lower() and "chain" not in body.lower():
            continue
        entries.append({
            "autoissue_id": row.pk,
            "title": row.title,
            "severity": row.severity,
            "category": row.category.key if row.category_id else "",
            "first_seen": row.first_seen.isoformat() if row.first_seen else "",
            "last_seen": row.last_seen.isoformat() if row.last_seen else "",
            "trap_or_cause": (row.lessons_learned or row.description or "")[:300],
        })
        if len(entries) >= limit:
            break
    return entries


def _write_audit_entry(task_id: str, agent: str, result_count: int) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "task_id": task_id,
        "agent": agent,
        "looked_up_at": _now_iso(),
        "result_count": int(result_count),
        "source": "disk-index" if INDEX_PATH.exists() else "db-fallback",
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


class Command(BaseCommand):
    help = (
        "Search prior commit failures and record the lookup in the disk-backed "
        "audit log so the pre-commit hook accepts the commit. Run once per task."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Max rows to print (default 10).",
        )
        parser.add_argument(
            "--agent",
            default="",
            help="Override the agent name recorded in the audit log.",
        )

    def handle(self, *args, **opts) -> None:
        limit = max(1, int(opts.get("limit") or 10))
        agent_raw = (opts.get("agent") or "").strip().lower()
        agent = agent_raw if agent_raw in {
            "claude", "codex", "gemini", "antigravity"
        } else "claude"

        rows = _load_disk_index()
        if not rows:
            rows = _query_db_fallback(limit)
            source = "db-fallback"
        else:
            source = "disk-index"

        rows = rows[:limit]
        task_id = resolved_issue_index.current_task_id()
        _write_audit_entry(task_id, agent, len(rows))

        if not rows:
            self.stdout.write(
                "[COMMIT FAILURES SEARCH: 0 matches — no prior commit failures recorded yet]"
            )
            return

        self.stdout.write(
            f"[COMMIT FAILURES SEARCH: {len(rows)} prior failure(s) — read before committing — source={source} task_id={task_id}]"
        )
        for row in rows:
            title = row.get("title") or row.get("failure_title") or "(no title)"
            seen = (
                row.get("last_seen")
                or row.get("date_failed")
                or row.get("first_seen")
                or "?"
            )[:10]
            severity = row.get("severity", "")
            self.stdout.write(
                f"  #{row.get('autoissue_id', '?')} ({seen}) [{severity}] {str(title)[:100]}"
            )
            cause = row.get("root_cause") or row.get("trap_or_cause") or ""
            if cause:
                first_line = str(cause).strip().splitlines()[0][:200]
                self.stdout.write(f"      cause: {first_line}")
