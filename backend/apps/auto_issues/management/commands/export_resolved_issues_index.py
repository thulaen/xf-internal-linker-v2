"""Export resolved AutoIssue rows to audit/resolved_issues_index.jsonl.

The Postgres pgdata volume is the primary store for resolved issue history.
This command exports a survivability snapshot to JSONL so the disk-backed
audit log + pre-edit hook keep working even after a database wipe or restore.

The exporter walks every resolved AutoIssue row and emits one JSON line per
(row, file_path) pair, parsing the `lessons_learned` field into the 11
required output fields per docs/PER-FILE-LESSON-LOOKUP-RULE.md.

Run idempotently before any commit that depends on a fresh index, and from
the post-resolve hook so the snapshot stays warm.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import resolved_issue_index


# Parse a `Trap: ... Fix shape: ...` lessons_learned body into the
# user-defined output fields. Best-effort: missing parts become "".
_TRAP_RE = re.compile(r"Trap:\s*(?P<trap>.+?)(?=\n[A-Z][a-z]+ ?[A-Za-z]*:|$)", re.DOTALL)
_FIX_RE = re.compile(r"Fix shape:\s*(?P<fix>.+?)(?=\n[A-Z][a-z]+ ?[A-Za-z]*:|$)", re.DOTALL)
_REFACTOR_RE = re.compile(r"Refactor:\s*(?P<r>.+?)(?=\n[A-Z][a-z]+ ?[A-Za-z]*:|$)", re.DOTALL)
_COVERAGE_RE = re.compile(r"Coverage:\s*(?P<c>.+?)(?=\n[A-Z][a-z]+ ?[A-Za-z]*:|$)", re.DOTALL)


class Command(BaseCommand):
    help = "Export resolved AutoIssue rows to the disk-backed JSONL index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of rows exported (0 = unlimited, default).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute what would be exported and print counts without writing.",
        )

    def handle(self, *args, **opts):
        limit = max(0, int(opts.get("limit") or 0))
        qs = AutoIssue.objects.filter(status=AutoIssue.STATUS_RESOLVED).order_by("-resolved_at")
        if limit:
            qs = qs[:limit]

        entries = list(_explode_rows(qs))

        if opts.get("dry_run"):
            self.stdout.write(
                f"[RESOLVED INDEX DRY-RUN: would write {len(entries)} entries "
                f"to {resolved_issue_index.INDEX_PATH.relative_to(resolved_issue_index.REPO_ROOT)}]"
            )
            return

        count = resolved_issue_index.write_index(entries)
        self.stdout.write(
            f"[RESOLVED INDEX EXPORTED: rows={count} "
            f"file={resolved_issue_index.INDEX_PATH.relative_to(resolved_issue_index.REPO_ROOT)}]"
        )


def _classify_affected(affected: list) -> tuple[list[str], list[str]]:
    """Split affected file paths into (test_paths, source_paths)."""
    tests: list[str] = []
    related: list[str] = []
    for f in affected:
        f_str = str(f).strip()
        if not f_str:
            continue
        lower = f_str.lower()
        if "test" in lower or "_spec" in lower or "spec.ts" in lower:
            tests.append(f_str)
        else:
            related.append(f_str)
    return tests, related


def _explode_rows(rows: Iterable[AutoIssue]) -> Iterable[dict[str, Any]]:
    """Yield one entry per (row, affected_file) pair."""
    for row in rows:
        affected = list(row.affected_files or [])
        if not affected:
            # Row has no affected file recorded; skip rather than fabricate.
            continue
        body = row.lessons_learned or ""
        trap = _first_group(_TRAP_RE, body)
        fix = _first_group(_FIX_RE, body)
        refactor = _first_group(_REFACTOR_RE, body)
        coverage = _first_group(_COVERAGE_RE, body)
        tests, related = _classify_affected(affected)
        for file_path in affected:
            file_path = str(file_path).strip()
            if not file_path:
                continue
            yield {
                "file_path": file_path,
                "issue_title": (row.title or "")[:200],
                "date_resolved": (
                    row.resolved_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if row.resolved_at
                    else ""
                ),
                "root_cause": trap,
                "what_failed": trap,
                "what_fixed_it": fix,
                "regression_risk": refactor or coverage,
                "tests_added_or_changed": tests,
                "related_files": [r for r in related if r != file_path],
                "patterns_to_avoid": [trap] if trap else [],
                "safe_implementation_notes": fix,
                "autoissue_id": row.pk,
                "source": f"AutoIssue:#{row.pk}",
                "category": row.category.key if row.category_id else "",
                "concept_tags": list(row.concept_tags or []),
            }


def _first_group(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    body = match.group(1).strip()
    # Collapse newlines and double spaces; the index is one-line-per-entry.
    return re.sub(r"\s+", " ", body)
