"""Parse MegaLinter's mega-linter-report.json and file deduped AutoIssues.

Reads MegaLinter's JSON report (from --stdin or --input-file) and creates
one AutoIssue per linter that reported errors, using the linter→category
mapping in megalinter_mapper.py. Formatting-only linters are skipped.
Duplicate findings are merged via the shared upsert_dedup engine.

Supports --dry-run so it can be called without writing to the database.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.megalinter_mapper import lookup

_HASH_LEN = 16


class Command(BaseCommand):
    help = "File AutoIssues for MegaLinter findings."

    def add_arguments(self, parser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--stdin",
            action="store_true",
            help="Read MegaLinter JSON report from stdin.",
        )
        group.add_argument(
            "--input-file",
            metavar="PATH",
            help="Path to mega-linter-report.json.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report counts without writing AutoIssues.",
        )

    def handle(self, *args, **opts) -> None:
        if opts["stdin"]:
            raw = sys.stdin.read()
        else:
            path = Path(opts["input_file"])
            if not path.is_file():
                raise CommandError(f"--input-file {path} does not exist or is not a file.")
            raw = path.read_text(encoding="utf-8", errors="replace")

        try:
            report = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON from MegaLinter report: {exc}") from exc

        linters = report.get("linters", [])
        if not isinstance(linters, list):
            raise CommandError("MegaLinter report 'linters' field is not a list.")

        created = merged = skipped = 0
        for entry in linters:
            linter_id = entry.get("id") or entry.get("descriptor_id", "UNKNOWN")
            status = entry.get("status", "success")
            n_errors = int(entry.get("number_errors", 0))

            if status == "success" or n_errors == 0:
                continue

            category_key, severity, enabled = lookup(linter_id)
            if not enabled:
                skipped += 1
                continue

            affected = _extract_files(entry)
            fingerprint = _fingerprint(linter_id, affected)
            external_id = f"megalinter:{linter_id}:{fingerprint}"

            if opts["dry_run"]:
                created += 1
                continue

            _, action = upsert_dedup(
                canonical=fingerprint,
                source=AutoIssue.SOURCE_MEGALINTER,
                external_id=external_id,
                fingerprint=fingerprint,
                title=f"[MegaLinter:{linter_id}] {n_errors} error(s)"[:200],
                description=_description(entry, linter_id, n_errors),
                affected_files=affected,
                severity=_map_severity(severity),
                priority_score=0.6 if severity in ("critical", "high") else 0.3,
                occurrence_count=1,
                category_key=category_key,
            )
            if action == "created":
                created += 1
            else:
                merged += 1

        label = "[MEGALINTER INGEST (dry-run)" if opts["dry_run"] else "[MEGALINTER INGEST"
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: linters_checked={len(linters)} "
                f"created={created} merged={merged} skipped={skipped}]"
            )
        )


def _extract_files(entry: dict) -> list[str]:
    files = entry.get("files") or entry.get("files_with_errors") or []
    if not isinstance(files, list):
        return []
    return [str(f) for f in files if f][:20]  # cap to avoid oversized DB fields


def _fingerprint(linter_id: str, files: list[str]) -> str:
    key = f"megalinter:{linter_id}:{','.join(sorted(files[:5]))}"
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:_HASH_LEN]


def _description(entry: dict, linter_id: str, n_errors: int) -> str:
    stdout_snippet = (entry.get("stdout") or "")[:500].strip()
    files = _extract_files(entry)
    parts = [f"Linter: {linter_id}", f"Errors: {n_errors}"]
    if files:
        parts.append("Files: " + ", ".join(files[:5]))
    if stdout_snippet:
        parts.append(f"Output: {stdout_snippet}")
    return "\n".join(parts)[:2000]


def _map_severity(severity: str) -> str:
    mapping = {
        "critical": AutoIssue.SEVERITY_CRITICAL,
        "high": AutoIssue.SEVERITY_HIGH,
        "medium": AutoIssue.SEVERITY_MEDIUM,
        "low": AutoIssue.SEVERITY_LOW,
    }
    return mapping.get(severity, AutoIssue.SEVERITY_MEDIUM)
