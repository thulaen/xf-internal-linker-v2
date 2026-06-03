"""Drain buffered hook findings into AutoIssues."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.auto_issues.management.commands.file_hook_finding import file_hook_finding


def backend_health_ok() -> bool:
    """Return whether the backend proof command is healthy."""
    try:
        call_command("verify_chain_batch", "--health", "--json")
    except BaseException:  # noqa: BLE001 - drain must not block session start.
        return False
    return True


class Command(BaseCommand):
    help = "Drain audit/findings_buffer.jsonl into AutoIssues."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--repo-root", default="/repo")

    def handle(self, *args, **options) -> None:
        repo_root = Path(options["repo_root"])
        audit_dir = repo_root / "audit"
        buffer_path = audit_dir / "findings_buffer.jsonl"
        audit_dir.mkdir(parents=True, exist_ok=True)
        if not backend_health_ok():
            self.stdout.write("[FINDINGS DRAIN SKIPPED: backend unreachable, retry next session]")
            return
        if not buffer_path.exists():
            buffer_path.write_text("", encoding="utf-8")
            self.stdout.write("[FINDINGS DRAINED: filed=0 deduped=0 total=0]")
            return
        filed, deduped = _process_buffer(buffer_path, audit_dir)
        _rotate_buffer(buffer_path)
        total = filed + deduped
        self.stdout.write(f"[FINDINGS DRAINED: filed={filed} deduped={deduped} total={total}]")


def _process_buffer(buffer_path: Path, audit_dir: Path) -> tuple[int, int]:
    filed = 0
    deduped = 0
    for raw in buffer_path.read_text(encoding="utf-8").splitlines():
        payload = _parse_line(raw, audit_dir)
        if payload is None:
            continue
        _, created = file_hook_finding(
            category=payload["category"],
            severity=payload["severity"],
            subject=payload["subject"],
            message=payload["message"],
            agent=payload.get("agent", "codex"),
        )
        if created:
            filed += 1
        else:
            deduped += 1
    return filed, deduped


def _parse_line(raw: str, audit_dir: Path) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _append_error(audit_dir, raw, str(exc))
        return None


def _append_error(audit_dir: Path, raw: str, parse_error: str) -> None:
    path = audit_dir / "findings_buffer.errors.jsonl"
    payload = {"line": raw, "parse_error": parse_error}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _rotate_buffer(buffer_path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    drained = buffer_path.with_name(f"findings_buffer.drained.{stamp}.jsonl")
    buffer_path.replace(drained)
    buffer_path.write_text("", encoding="utf-8")
