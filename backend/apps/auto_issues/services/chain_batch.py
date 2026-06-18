"""Batch verification helpers for commit-chain database checks."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path
from typing import Any

from django.core.checks import run_checks
from django.db import connection
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services.evidence import (
    validate_citation,
    validate_test_case_completeness,
)

Result = dict[str, Any]
BatchResult = dict[str, dict[str, Result] | Result]

_AUTOISSUE_GROUPS = {
    "tdd_lessons": "tdd_lesson",
    "test_cases": "test_case",
    "code_review_lessons": "code_review_lesson",
}
_AUTOISSUE_FIELDS = (
    "id",
    "category__key",
    "source",
    "external_id",
    "status",
    "lessons_learned",
    "canonical_fingerprint",
    "resolved_at",
)
_PAPER_FIELDS = (
    "id",
    "status",
    "resolution_lessons",
    "canonical_fingerprint",
    "resolved_at",
    "deferred_at",
    "abstract",
    "risk_on_inaction",
    "acceptance_criteria",
    "test_case_autoissue_id",
    "citations",
)
_EVIDENCE_CUTOFF = datetime(2026, 5, 17, 7, 25, 0, tzinfo=dt_tz.utc)
_RESOLUTION_EVIDENCE_CUTOFF = datetime(2026, 5, 23, 18, 0, 0, tzinfo=dt_tz.utc)
_ISSUE_REFERENCE_RE = re.compile(r"#(?P<id>\d+)")


def batch_verify(
    categories: dict[str, list[int]],
    *,
    resolved_after: datetime | None = None,
) -> BatchResult:
    """Verify all requested commit-chain groups with bounded queries."""
    result: BatchResult = {}
    for group, expected_category in _AUTOISSUE_GROUPS.items():
        ids = _unique_ids(categories.get(group, []))
        if ids:
            result[group] = _verify_autoissue_group(ids, expected_category, group)
    if categories.get("autoissue_quota"):
        result["autoissue_quota"] = _verify_autoissue_quota(
            categories["autoissue_quota"],
            resolved_after,
        )
    if categories.get("paper_trail_quota"):
        result["paper_trail_quota"] = _verify_paper_quota(
            categories["paper_trail_quota"],
            resolved_after,
        )
    if categories.get("paper_trail_evidence"):
        ids = _unique_ids(categories["paper_trail_evidence"])
        result["paper_trail_evidence"] = _verify_paper_evidence(ids)
    return result


def health_report(*, helper_log_path: Path | None = None) -> tuple[int, Result]:
    """Return exit code plus health details for the batch verifier."""
    report: Result = {
        "postgres": "ok",
        "backend": "ok",
        "auto_issues_table": "ok",
        "helper_failure_rate_per_hour": 0,
        "buffer_unflushed_count": 0,
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        report["postgres"] = f"down: {exc}"
        return 1, report
    try:
        run_checks()
        AutoIssue.objects.exists()
    except Exception as exc:  # noqa: BLE001
        report["backend"] = f"down: {exc}"
        report["auto_issues_table"] = f"down: {exc}"
        return 1, report
    report.update(_helper_failure_stats(helper_log_path or Path("audit/helper_failures.jsonl")))
    return 0, report


def _verify_autoissue_group(
    ids: list[int],
    expected_category: str,
    group: str,
) -> dict[str, Result]:
    rows = _autoissue_rows(ids)
    result: dict[str, Result] = {}
    for issue_id in ids:
        row = rows.get(issue_id)
        if row is None:
            result[str(issue_id)] = _fail("does not exist")
            continue
        result[str(issue_id)] = _autoissue_group_result(row, expected_category, group)
    return result


def _autoissue_group_result(row: dict[str, Any], expected_category: str, group: str) -> Result:
    category = row.get("category__key") or "(no category)"
    if category != expected_category:
        return _fail(f"wrong category: {category}")
    if group != "test_cases" and row.get("status") != AutoIssue.STATUS_RESOLVED:
        return _fail(f"wrong status: {row.get('status')}")
    lessons = (row.get("lessons_learned") or "").strip()
    if group == "test_cases":
        return _test_case_result(lessons)
    if group == "tdd_lessons" and ("Trap:" not in lessons or "Fix shape:" not in lessons):
        return _fail("missing Trap and Fix shape lesson")
    return _pass()


def _verify_autoissue_quota(ids: list[int], resolved_after: datetime | None) -> Result:
    errors = _quota_count_errors(ids, 28, "AutoIssue")
    rows = _autoissue_rows(ids)
    errors.extend(_missing_errors(ids, rows, "AutoIssue"))
    errors.extend(_duplicate_canonical_errors(ids, rows, "AutoIssue"))
    for issue_id in ids:
        row = rows.get(issue_id)
        if row is not None:
            errors.extend(_autoissue_quota_row_errors(issue_id, row, resolved_after))
    return _fail("; ".join(errors)) if errors else _pass()


def _verify_paper_quota(ids: list[int], resolved_after: datetime | None) -> Result:
    errors = _quota_count_errors(ids, 10, "PaperTrailEntry")
    rows = _paper_rows(ids)
    errors.extend(_missing_errors(ids, rows, "PaperTrailEntry"))
    errors.extend(_duplicate_canonical_errors(ids, rows, "PaperTrailEntry"))
    for entry_id in ids:
        row = rows.get(entry_id)
        if row is not None:
            errors.extend(_paper_quota_row_errors(entry_id, row, resolved_after))
    return _fail("; ".join(errors)) if errors else _pass()


def _verify_paper_evidence(ids: list[int]) -> dict[str, Result]:
    rows = _paper_rows(ids)
    test_case_ids = [
        row["test_case_autoissue_id"]
        for row in rows.values()
        if row.get("test_case_autoissue_id") is not None
    ]
    test_cases = _autoissue_rows(test_case_ids)
    code_reviews = _autoissue_rows(_paper_resolution_review_ids(rows.values()))
    return {
        str(entry_id): _paper_evidence_result(
            entry_id,
            rows.get(entry_id),
            test_cases,
            code_reviews,
        )
        for entry_id in ids
    }


def _paper_evidence_result(
    entry_id: int,
    row: dict[str, Any] | None,
    test_cases: dict[int, dict[str, Any]],
    code_reviews: dict[int, dict[str, Any]],
) -> Result:
    if row is None:
        return _pass()
    if row["deferred_at"] is not None and row["deferred_at"] < _EVIDENCE_CUTOFF:
        return _pass()
    errors = _paper_evidence_core_errors(row)
    tc_id = row.get("test_case_autoissue_id")
    tc = test_cases.get(tc_id) if tc_id is not None else None
    errors.extend(_paper_evidence_test_case_errors(tc_id, tc))
    errors.extend(_paper_evidence_citation_errors(row))
    errors.extend(_paper_evidence_resolution_errors(row, code_reviews))
    return _fail(f"#{entry_id}: " + "; ".join(errors)) if errors else _pass()


def _paper_evidence_core_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("abstract", "risk_on_inaction", "acceptance_criteria"):
        if not (row.get(field) or "").strip():
            errors.append(f"missing {field}")
    abstract = (row.get("abstract") or "").lower()
    for keyword in ("given", "when", "then"):
        if keyword not in abstract:
            errors.append(f"abstract missing {keyword.title()}")
    return errors


def _paper_evidence_test_case_errors(
    tc_id: int | None,
    tc: dict[str, Any] | None,
) -> list[str]:
    if tc_id is None:
        return ["missing test_case_autoissue_id"]
    if tc is None:
        return [f"linked AutoIssue #{tc_id} does not exist"]
    if tc.get("category__key") != "test_case":
        return [f"linked AutoIssue #{tc_id} is not test_case"]
    missing = validate_test_case_completeness(_DictAutoIssue(tc))
    return [f"test case missing {', '.join(missing)}"] if missing else []


def _paper_evidence_citation_errors(row: dict[str, Any]) -> list[str]:
    citations = row.get("citations") or []
    if not citations:
        return ["missing citations"]
    bad = [citation for citation in citations if not validate_citation(citation)[0]]
    return [f"invalid citations: {', '.join(bad[:5])}"] if bad else []


def _paper_resolution_review_ids(rows: list[dict[str, Any]]) -> list[int]:
    seen: dict[int, None] = {}
    for row in rows:
        if _requires_resolution_evidence(row):
            for issue_id in _referenced_issue_ids(row.get("resolution_lessons") or ""):
                seen.setdefault(issue_id, None)
    return list(seen.keys())


def _paper_evidence_resolution_errors(
    row: dict[str, Any],
    code_reviews: dict[int, dict[str, Any]],
) -> list[str]:
    if not _requires_resolution_evidence(row):
        return []
    if row.get("resolved_at") is None:
        return ["resolved entry has no resolved_at time"]
    referenced = _referenced_issue_ids(row.get("resolution_lessons") or "")
    for issue_id in referenced:
        review = code_reviews.get(issue_id)
        if _is_resolved_code_review(review):
            return []
    return ["missing resolved code_review_lesson reference"]


def _requires_resolution_evidence(row: dict[str, Any]) -> bool:
    if row.get("status") != PaperTrailEntry.STATUS_RESOLVED:
        return False
    resolved_at = row.get("resolved_at")
    if resolved_at is None:
        return True
    return resolved_at >= _RESOLUTION_EVIDENCE_CUTOFF


def _referenced_issue_ids(text: str) -> list[int]:
    seen: dict[int, None] = {}
    for match in _ISSUE_REFERENCE_RE.finditer(text or ""):
        seen.setdefault(int(match.group("id")), None)
    return list(seen.keys())


def _is_resolved_code_review(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("category__key") == "code_review_lesson"
        and row.get("status") == AutoIssue.STATUS_RESOLVED
    )


def _autoissue_quota_row_errors(
    issue_id: int,
    row: dict[str, Any],
    resolved_after: datetime | None,
) -> list[str]:
    errors: list[str] = []
    if row["status"] != AutoIssue.STATUS_RESOLVED:
        errors.append(f"#{issue_id} is {row['status']}, not resolved")
    errors.extend(_resolved_time_errors(issue_id, row.get("resolved_at"), resolved_after))
    if not (row.get("lessons_learned") or "").strip():
        errors.append(f"#{issue_id} has no lessons_learned note")
    return errors


def _paper_quota_row_errors(
    entry_id: int,
    row: dict[str, Any],
    resolved_after: datetime | None,
) -> list[str]:
    errors: list[str] = []
    if row["status"] != PaperTrailEntry.STATUS_RESOLVED:
        errors.append(f"#{entry_id} is {row['status']}, not resolved")
    errors.extend(_resolved_time_errors(entry_id, row.get("resolved_at"), resolved_after))
    lessons = (row.get("resolution_lessons") or "").strip()
    if "Trap:" not in lessons or "Fix shape:" not in lessons:
        errors.append(f"#{entry_id} has malformed resolution_lessons")
    return errors


def _test_case_result(lessons: str) -> Result:
    missing = [
        label
        for label in ("Given", "When", "Then")
        if label.lower() not in lessons.lower()
    ]
    return _fail(f"missing {', '.join(missing)}") if missing else _pass()


def _autoissue_rows(ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    return {
        row["id"]: row
        for row in AutoIssue.objects.filter(id__in=ids).values(*_AUTOISSUE_FIELDS)
    }


def _paper_rows(ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    return {
        row["id"]: row
        for row in PaperTrailEntry.objects.filter(id__in=ids).values(*_PAPER_FIELDS)
    }


def _quota_count_errors(ids: list[int], expected: int, label: str) -> list[str]:
    errors: list[str] = []
    if len(ids) != expected:
        errors.append(f"expected {expected} {label} ids, got {len(ids)}")
    if len(set(ids)) != len(ids):
        errors.append(f"duplicate {label} ids are not allowed")
    return errors





def _missing_errors(ids: list[int], rows: dict[int, dict[str, Any]], label: str) -> list[str]:
    missing = [entry_id for entry_id in ids if entry_id not in rows]
    if not missing:
        return []
    return [f"missing {label} ids: {_render_ids(missing)}"]


def _duplicate_canonical_errors(
    ids: list[int],
    rows: dict[int, dict[str, Any]],
    label: str,
) -> list[str]:
    by_key: dict[str, list[int]] = {}
    for entry_id in ids:
        key = (rows.get(entry_id) or {}).get("canonical_fingerprint")
        if key:
            by_key.setdefault(key, []).append(entry_id)
    duplicates = [_render_ids(found) for found in by_key.values() if len(found) > 1]
    return [f"duplicate {label} work: {'; '.join(duplicates)}"] if duplicates else []


def _resolved_time_errors(
    entry_id: int,
    resolved_at: datetime | None,
    resolved_after: datetime | None,
) -> list[str]:
    if resolved_at is None:
        return [f"#{entry_id} has no resolved_at time"]
    if resolved_after and resolved_at <= resolved_after:
        return [f"#{entry_id} was resolved before the cutoff"]
    return []


def _helper_failure_stats(path: Path) -> Result:
    cutoff = timezone.now() - timedelta(hours=1)
    failures = 0
    unflushed = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"helper_failure_rate_per_hour": 0, "buffer_unflushed_count": 0}
    for line in lines:
        failures += _line_failed_within_hour(line, cutoff)
        unflushed += 1 if '"flushed": false' in line.lower() else 0
    return {"helper_failure_rate_per_hour": failures, "buffer_unflushed_count": unflushed}


def _line_failed_within_hour(line: str, cutoff: datetime) -> int:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return 0
    raw = payload.get("failed_at")
    if not raw:
        return 0
    try:
        failed_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(failed_at >= cutoff)


def _unique_ids(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _pass() -> Result:
    return {"status": "pass"}


def _fail(reason: str) -> Result:
    return {"status": "fail", "reason": reason}


def _render_ids(ids: list[int]) -> str:
    return ", ".join(f"#{entry_id}" for entry_id in ids)


class _DictAutoIssue:
    def __init__(self, row: dict[str, Any]) -> None:
        self.lessons_learned = row.get("lessons_learned") or ""
