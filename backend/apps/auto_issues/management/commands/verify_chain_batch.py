"""Verify many commit-chain database proofs in one backend command."""

from __future__ import annotations

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.auto_issues.services.chain_batch import batch_verify, health_report


class Command(BaseCommand):
    help = "Batch verify commit-chain proof IDs and quota IDs."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tdd-lessons", default="")
        parser.add_argument("--test-cases", default="")
        parser.add_argument("--code-review-lessons", default="")
        parser.add_argument("--autoissue-quota", default="")
        parser.add_argument("--paper-trail-quota", default="")
        parser.add_argument("--paper-trail-evidence", default="")
        parser.add_argument("--resolved-after", default=None)
        parser.add_argument("--health", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **opts) -> None:
        if opts["health"]:
            exit_code, report = health_report()
            self._write(report, as_json=opts["as_json"])
            if exit_code:
                raise SystemExit(exit_code)
            return

        categories = _categories_from_opts(opts)
        resolved_after = _parse_resolved_after(opts.get("resolved_after"))
        result = batch_verify(categories, resolved_after=resolved_after)
        self._write(result, as_json=opts["as_json"])

    def _write(self, payload, *, as_json: bool) -> None:
        if as_json:
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))


def _categories_from_opts(opts: dict) -> dict[str, list[int]]:
    return {
        "tdd_lessons": _parse_csv(opts["tdd_lessons"], "--tdd-lessons"),
        "test_cases": _parse_csv(opts["test_cases"], "--test-cases"),
        "code_review_lessons": _parse_csv(
            opts["code_review_lessons"],
            "--code-review-lessons",
        ),
        "autoissue_quota": _parse_csv(opts["autoissue_quota"], "--autoissue-quota"),
        "paper_trail_quota": _parse_csv(
            opts["paper_trail_quota"],
            "--paper-trail-quota",
        ),
        "paper_trail_evidence": _parse_csv(
            opts["paper_trail_evidence"],
            "--paper-trail-evidence",
        ),
    }


def _parse_csv(raw: str, flag: str) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.split(","):
        value = part.strip().removeprefix("#")
        if not value:
            continue
        try:
            ids.append(int(value))
        except ValueError as exc:
            raise CommandError(f"{flag} must be a comma-separated list of IDs.") from exc
    return ids


def _parse_resolved_after(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if connection.timezone is not None:
                parsed = parsed.replace(tzinfo=connection.timezone)
            return parsed
        except ValueError:
            continue
    raise CommandError("--resolved-after must use YYYY-MM-DD HH:MM or ISO 8601.")
