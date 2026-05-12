"""Programmatic appender for docs/reports/REPORT-REGISTRY.md.

Phase 6 follow-up of the test-hardening plan, landed under FR-251.

Called by the 5 new pickers (mutation, fuzz, lint_error, contract_drift,
ci_failed_runs) after `upsert_dedup(...)` returns ``'created'`` for a
high-severity row. The command:

1. Reads `docs/reports/REPORT-REGISTRY.md` from the repo root.
2. Finds the highest existing ``### RPT-NNN`` heading.
3. Appends a new ``### RPT-<NNN+1>`` entry block whose body matches the
   shape of RPT-007 (Found by / AutoIssue / Status / Severity / Area /
   plain English / why it matters / fix shape).
4. **Idempotency:** before appending, scans the file for the AutoIssue's
   `canonical_fingerprint` in any existing entry; if found, skips with
   a "duplicate; not appending" log line.

Run manually (one AutoIssue → one registry entry):
    docker compose exec -T backend python manage.py \\
        auto_issues_append_registry --issue-id 163

Run for every high-severity AutoIssue created today:
    docker compose exec -T backend python manage.py \\
        auto_issues_append_registry --since today --severity high
"""

# print-allowed: this is a management command — stdout is the API contract.

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.models import AutoIssue

logger = logging.getLogger(__name__)


_RPT_HEADING_RE = re.compile(r"^### RPT-(\d{3,4}) ", re.MULTILINE)
_OPEN_REPORTS_RE = re.compile(r"^## Open Reports\s*$", re.MULTILINE)


class Command(BaseCommand):
    help = (
        "Append a new RPT-<NNN> entry to docs/reports/REPORT-REGISTRY.md "
        "for one or more AutoIssue rows. Idempotent — duplicate "
        "canonical_fingerprints are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--issue-id",
            type=int,
            help="AutoIssue id to append. Repeat for multiple issues.",
            action="append",
            default=[],
        )
        parser.add_argument(
            "--since",
            help=(
                "Append entries for AutoIssues created since this date "
                "(YYYY-MM-DD or 'today'). Combined with --severity to filter."
            ),
        )
        parser.add_argument(
            "--severity",
            choices=[c[0] for c in AutoIssue.SEVERITY_CHOICES],
            help="Restrict to AutoIssues with this severity.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the entry that would be appended; do not write the file.",
        )

    def handle(self, *args, **opts):
        registry_path = self._registry_path()
        existing = registry_path.read_text(encoding="utf-8")

        issues = self._collect_issues(opts)
        if not issues:
            self.stdout.write("auto_issues_append_registry: no matching AutoIssues; nothing to do")
            return

        next_id = self._next_rpt_id(existing)
        appended = 0
        skipped = 0
        for issue in issues:
            if self._already_in_registry(existing, issue):
                self.stdout.write(
                    f"  SKIPPED #{issue.id} — canonical_fingerprint already in registry"
                )
                skipped += 1
                continue
            entry = self._format_entry(next_id, issue)
            if opts["dry_run"]:
                self.stdout.write("---- DRY RUN — would append ----")
                self.stdout.write(entry)
                self.stdout.write("---- END DRY RUN ----")
            else:
                existing = self._insert_under_open_reports(existing, entry)
                self.stdout.write(f"  APPENDED RPT-{next_id:03d} for AutoIssue #{issue.id}")
            next_id += 1
            appended += 1

        if not opts["dry_run"] and appended:
            registry_path.write_text(existing, encoding="utf-8")
            self.stdout.write(
                f"auto_issues_append_registry: appended {appended}, skipped {skipped}"
            )
        elif opts["dry_run"]:
            self.stdout.write(
                f"auto_issues_append_registry: would append {appended}, skipped {skipped} (dry-run)"
            )

    # ─── helpers ────────────────────────────────────────────────────

    def _registry_path(self) -> Path:
        """Locate REPORT-REGISTRY.md across host/container scenarios.

        Search order:
          1. ``BASE_DIR.parent / docs / reports / REPORT-REGISTRY.md`` — typical
             host setup where BASE_DIR is ``<repo>/backend/``.
          2. ``BASE_DIR / docs / reports / REPORT-REGISTRY.md`` — host setup
             where BASE_DIR points at the repo root.
          3. ``/repo/docs/reports/REPORT-REGISTRY.md`` — the docker-compose
             read-only mount of the host repo into the backend container.
             Note: this path is READ-ONLY when accessed from the container
             — append operations from inside Celery will fail at write
             time. Run the command from the host, or mount docs/ writable
             into the container (a Phase 8+ follow-up).
        """
        base = getattr(settings, "BASE_DIR", Path.cwd())
        candidates = [
            Path(base).parent / "docs" / "reports" / "REPORT-REGISTRY.md",
            Path(base) / "docs" / "reports" / "REPORT-REGISTRY.md",
            Path("/repo/docs/reports/REPORT-REGISTRY.md"),
        ]
        for p in candidates:
            if p.is_file():
                return p
        raise CommandError(f"REPORT-REGISTRY.md not found at any of: {candidates}")

    def _collect_issues(self, opts) -> list[AutoIssue]:
        if opts["issue_id"]:
            return list(
                AutoIssue.objects.filter(id__in=opts["issue_id"]).order_by("id")
            )
        qs = AutoIssue.objects.all()
        if opts["since"]:
            cutoff = self._parse_since(opts["since"])
            qs = qs.filter(first_seen__gte=cutoff)
        if opts["severity"]:
            qs = qs.filter(severity=opts["severity"])
        return list(qs.order_by("id"))

    @staticmethod
    def _parse_since(s: str) -> dt.datetime:
        if s == "today":
            return dt.datetime.combine(dt.date.today(), dt.time.min, tzinfo=dt.timezone.utc)
        try:
            return dt.datetime.combine(
                dt.date.fromisoformat(s), dt.time.min, tzinfo=dt.timezone.utc
            )
        except ValueError as e:
            raise CommandError(f"Invalid --since value: {s} (use YYYY-MM-DD or 'today')") from e

    @staticmethod
    def _next_rpt_id(existing: str) -> int:
        ids = [int(m.group(1)) for m in _RPT_HEADING_RE.finditer(existing)]
        return (max(ids) + 1) if ids else 1

    @staticmethod
    def _already_in_registry(existing: str, issue: AutoIssue) -> bool:
        if not issue.canonical_fingerprint:
            return False
        return issue.canonical_fingerprint in existing

    @staticmethod
    def _format_entry(rpt_id: int, issue: AutoIssue) -> str:
        today = dt.date.today().isoformat()
        files = ", ".join(f"`{f}`" for f in (issue.affected_files or [])[:5]) or "_unspecified_"
        description = (issue.description or "").strip()
        # Take the first 2-3 lines for the plain-English body, full body
        # if it's short.
        short_desc = description if len(description) < 400 else description[:400].rsplit(" ", 1)[0] + " …"

        return (
            f"\n### RPT-{rpt_id:03d} - {issue.title[:90]} ({today})\n\n"
            f"- **Found by:** auto_issues_append_registry, from AutoIssue #{issue.id} "
            f"(source `{issue.source}`).\n"
            f"- **AutoIssue:** #{issue.id}.\n"
            f"- **Status:** OPEN.\n"
            f"- **Severity:** {issue.severity.upper()}.\n"
            f"- **Area:** {files}.\n"
            f"- **canonical_fingerprint:** `{issue.canonical_fingerprint}`.\n"
            f"- **What is wrong in plain English:** {short_desc}\n"
            f"- **Why it matters:** the AutoIssue picker that surfaced this is "
            f"part of the test-hardening or coverage program — leaving it open "
            f"means a real failure signal goes uninvestigated.\n"
            f"- **Fix shape:** see AutoIssue #{issue.id} for the full picker "
            f"description; the next agent picks this up during the standard "
            f"18-pick or 10-coverage-gap drain.\n\n"
            f"---\n"
        )

    @staticmethod
    def _insert_under_open_reports(existing: str, entry: str) -> str:
        """Insert *entry* directly under the `## Open Reports` heading."""
        match = _OPEN_REPORTS_RE.search(existing)
        if not match:
            # Fallback: append at the very end.
            return existing.rstrip() + "\n" + entry
        insert_at = match.end()
        return existing[:insert_at] + entry + existing[insert_at:]
