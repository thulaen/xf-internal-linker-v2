"""Read a Paper Trail sticky entry and emit the programmatic [STICKY N READ:] marker.

This command implements the read mechanism for the Sticky-Read Rule
(2026-05-23). Every agent must run `manage.py read_sticky --id 1` at
session start and paste the printed `[STICKY 1 READ: ...]` marker
verbatim into the AGENT-HANDOFF.md entry before any code is written.

The marker carries a 16-char SHA-256 prefix of the sticky body that
the pre-commit hook `.githooks/check-sticky-1-read.py` cross-checks
against the live sticky body to detect mid-session edits.

The command also appends an audit row to `audit/sticky_reads.jsonl`
recording the agent name, the timestamp, the sticky id, and the
SHA-256 prefix the agent received.

Run:
    python scripts/backend_manage.py read_sticky --id 1
    python scripts/backend_manage.py read_sticky --id 1 --print-sha-only
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.models import PaperTrailEntry


_AUDIT_PATH = Path("/repo/audit/sticky_reads.jsonl")


def _sha256_prefix(text: str, length: int = 16) -> str:
    """Return the first *length* hex chars of the SHA-256 of *text*."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:length]


def _agent_name_from_env() -> str:
    """Return the agent name from the env, defaulting to 'claude'."""
    return (os.environ.get("XF_AGENT_NAME") or "claude").strip() or "claude"


def _utc_now_iso() -> str:
    """Return current UTC time as a stable ISO-8601 string with trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_audit_row(path: Path, payload: dict[str, Any]) -> None:
    """Append one JSON record per line to the audit log (best-effort)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # Audit-log failure must not block the read. The marker on stdout
        # is the authoritative record; the JSONL is a convenience trail.
        pass


# xf: no_dry_run -- read_sticky is read-only on the paper_trail table; the only
# side effect is an append to audit/sticky_reads.jsonl which is intentional
# and idempotent (re-running the same read appends a new audit row, which is
# the desired record of every read attempt).
class Command(BaseCommand):
    """Print a sticky entry's body + SHA-256-verified read marker."""

    help = "Read a sticky Paper Trail entry and emit the programmatic read marker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            type=int,
            required=True,
            help="Paper Trail entry id of the sticky to read.",
        )
        parser.add_argument(
            "--print-sha-only",
            action="store_true",
            help="Print only the 16-char SHA-256 prefix (for hook use).",
        )

    def handle(self, *args, **options) -> None:
        sticky_number: int = options["id"]
        sha_only: bool = options["print_sha_only"]

        # The --id flag is a 1-based sticky sequence number (not the
        # paper_trail row primary key) so "Sticky #1" always means the
        # first sticky filed regardless of how many non-sticky entries
        # exist in the table. This matches the sticky body's own
        # references and the rule's `--id 1` convention.
        sticky_qs = PaperTrailEntry.objects.filter(
            status=PaperTrailEntry.STATUS_STICKY
        ).order_by("id")
        sticky_list = list(sticky_qs)

        if sticky_number < 1 or sticky_number > len(sticky_list):
            raise CommandError(
                f"sticky #{sticky_number} not found. There are "
                f"{len(sticky_list)} sticky entries; valid --id values "
                f"are 1 through {len(sticky_list)} (or 0 if none filed "
                "yet, in which case file one via manage.py log_sticky "
                "first)."
            )

        entry = sticky_list[sticky_number - 1]

        body = entry.abstract or ""
        sha_prefix = _sha256_prefix(body)

        if sha_only:
            self.stdout.write(sha_prefix)
            return

        agent = _agent_name_from_env()
        timestamp = _utc_now_iso()
        updated_at = (
            entry.deferred_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if entry.deferred_at
            else "unknown"
        )

        # 1) Full body to stdout for the agent to read.
        self.stdout.write(body)
        self.stdout.write("")

        # 2) Confirmation banner with last-updated timestamp + full hash.
        self.stdout.write(
            f"--- sticky #{sticky_number} (paper_trail row {entry.id}) "
            f"'{entry.title}' updated_at={updated_at} "
            f"sha256_prefix={sha_prefix} "
            f"word_count={len(body.split())} ---"
        )

        # 3) The programmatic read marker (verbatim copy into handoff).
        self.stdout.write(
            f"[STICKY {sticky_number} READ: timestamp={timestamp} "
            f"sha256={sha_prefix} agent={agent}]"
        )

        # 4) Append the audit row.
        _append_audit_row(
            _AUDIT_PATH,
            {
                "agent": agent,
                "timestamp": timestamp,
                "sticky_number": sticky_number,
                "paper_trail_id": entry.id,
                "sha256_prefix": sha_prefix,
            },
        )
