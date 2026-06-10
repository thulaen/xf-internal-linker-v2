"""Verify that a handoff's 30 picked AutoIssues were truly resolved."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


REQUIRED_AUTOISSUE_FIXES = 30
REQUIRED_RUST_DEFECT_FIXES = 10
REQUIRED_PPROF_FIXES = 10
REQUIRED_ALLOY_FIXES = 10
REQUIRED_LOKI_HARD_FIXES = 7
REQUIRED_PERFETTO_FIXES = 10
REQUIRED_GWP_ASAN_FIXES = 10
REQUIRED_LIGHTHOUSE_FIXES = 3
REQUIRED_PG_STAT_FIXES = 3
_CROSS_SOURCE_FIXES = 3
_RETIRED_HARD_SOURCES = frozenset(
    {
        AutoIssue.SOURCE_PPROF,
        AutoIssue.SOURCE_PERFETTO,
        AutoIssue.SOURCE_GWP_ASAN,
    }
)
_CONFIGURED_HARD_SOURCE_REQUIREMENTS = {
    AutoIssue.SOURCE_RUST_DEFECT: REQUIRED_RUST_DEFECT_FIXES,
    AutoIssue.SOURCE_PPROF: REQUIRED_PPROF_FIXES,
    AutoIssue.SOURCE_ALLOY: REQUIRED_ALLOY_FIXES,
    AutoIssue.SOURCE_LOKI: REQUIRED_LOKI_HARD_FIXES,
    AutoIssue.SOURCE_PERFETTO: REQUIRED_PERFETTO_FIXES,
    AutoIssue.SOURCE_GWP_ASAN: REQUIRED_GWP_ASAN_FIXES,
    AutoIssue.SOURCE_LIGHTHOUSE: REQUIRED_LIGHTHOUSE_FIXES,
    AutoIssue.SOURCE_PG_STAT: REQUIRED_PG_STAT_FIXES,
}
_HARD_SOURCE_REQUIREMENTS = {
    source: required
    for source, required in _CONFIGURED_HARD_SOURCE_REQUIREMENTS.items()
    if source not in _RETIRED_HARD_SOURCES
}
_CROSS_SOURCE_REQUIREMENTS = {
    AutoIssue.SOURCE_AGENT: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_GLITCHTIP: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_PYROSCOPE: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_TEMPO: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_FARO: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_MUTATION: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_FUZZ: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_CONTRACT: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_GH_CI: _CROSS_SOURCE_FIXES,
    AutoIssue.SOURCE_VMALERT: _CROSS_SOURCE_FIXES,
}
REQUIRED_HARD_FIXES = sum(_HARD_SOURCE_REQUIREMENTS.values()) + sum(
    _CROSS_SOURCE_REQUIREMENTS.values()
)


_SESSION_TYPE_CHOICES = ("docs", "infrastructure", "reconciliation", "feature")


def _scaled_requirements(
    session_type: str,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (hard_source_reqs, cross_source_reqs) scaled for session_type.

    reconciliation: hard buckets → 0, cross-source → 1 each (total 10).
    infrastructure: hard buckets → 0, cross-source → 2 each (total 20).
    docs:           both → 0 (gate passes immediately).
    feature:        unchanged full quotas.
    """
    if session_type == "docs":
        return {s: 0 for s in _HARD_SOURCE_REQUIREMENTS}, {
            s: 0 for s in _CROSS_SOURCE_REQUIREMENTS
        }
    if session_type == "reconciliation":
        return {s: 0 for s in _HARD_SOURCE_REQUIREMENTS}, {
            s: 1 for s in _CROSS_SOURCE_REQUIREMENTS
        }
    if session_type == "infrastructure":
        return {s: 0 for s in _HARD_SOURCE_REQUIREMENTS}, {
            s: 2 for s in _CROSS_SOURCE_REQUIREMENTS
        }
    # Default: feature — full quotas.
    return _HARD_SOURCE_REQUIREMENTS, _CROSS_SOURCE_REQUIREMENTS


class Command(BaseCommand):
    help = "Verify the 30 AutoIssue records named in the handoff are resolved."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--ids",
            nargs="+",
            required=False,
            help="AutoIssue IDs from the [REGISTRY READ] marker, without drought-log IDs.",
        )
        parser.add_argument(
            "--resolved-after",
            help="Previous handoff timestamp, formatted as YYYY-MM-DD HH:MM.",
        )
        parser.add_argument(
            "--hard",
            action="store_true",
            help="Verify the hard per-source quota for this session.",
        )
        parser.add_argument(
            "--session-type",
            choices=_SESSION_TYPE_CHOICES,
            default="feature",
            help=(
                "Session type scales the verify quota. "
                "docs=0, reconciliation=10, infrastructure=20, feature=103 (default)."
            ),
        )

    def handle(self, *args, **opts) -> None:
        resolved_after = _parse_resolved_after(opts.get("resolved_after"))
        session_type = opts.get("session_type") or "feature"

        if opts.get("hard"):
            hard_reqs, cross_reqs = _scaled_requirements(session_type)
            if session_type == "docs":
                self.stdout.write(
                    self.style.SUCCESS("[AUTOISSUE QUOTA VERIFIED: docs — no quota required]")
                )
                return
            errors = _hard_quota_errors_scaled(
                _resolved_counts(resolved_after), hard_reqs, cross_reqs
            )
            if errors:
                raise CommandError("\n".join(errors))
            total = sum(hard_reqs.values()) + sum(cross_reqs.values())
            self.stdout.write(
                self.style.SUCCESS(
                    f"[AUTOISSUE QUOTA VERIFIED: {total} resolved]"
                )
            )
            return

        if not opts.get("ids"):
            raise CommandError("--ids is required unless --hard is used.")
        issue_ids = _parse_issue_ids(opts["ids"])
        errors = _quota_errors(issue_ids, resolved_after)
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(
            self.style.SUCCESS(
                f"[AUTOISSUE QUOTA VERIFIED: {REQUIRED_AUTOISSUE_FIXES} resolved]"
            )
        )


def _parse_issue_ids(raw_ids: list[str]) -> list[int]:
    issue_ids: list[int] = []
    for raw_id in raw_ids:
        try:
            issue_ids.append(int(raw_id.strip().removeprefix("#")))
        except ValueError as exc:
            raise CommandError(f"AutoIssue ID must be a number: {raw_id}") from exc
    return issue_ids


def _parse_resolved_after(raw_stamp: str | None) -> datetime | None:
    if not raw_stamp:
        return None
    try:
        parsed = datetime.strptime(raw_stamp, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise CommandError(
            "--resolved-after must use YYYY-MM-DD HH:MM, for example 2026-05-13 05:45"
        ) from exc
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def _quota_errors(issue_ids: list[int], resolved_after: datetime | None) -> list[str]:
    errors = _count_and_duplicate_errors(issue_ids)
    if errors:
        return errors
    issues = {issue.id: issue for issue in AutoIssue.objects.filter(id__in=issue_ids)}
    errors.extend(_missing_issue_errors(issue_ids, issues))
    errors.extend(_duplicate_work_errors(issue_ids, issues))
    errors.extend(_issue_state_errors(issue_ids, issues, resolved_after))
    return errors


def _count_and_duplicate_errors(issue_ids: list[int]) -> list[str]:
    errors: list[str] = []
    if len(issue_ids) != REQUIRED_AUTOISSUE_FIXES:
        errors.append(
            f"Expected {REQUIRED_AUTOISSUE_FIXES} picked AutoIssues, found {len(issue_ids)}."
        )
    duplicates = sorted(
        issue_id for issue_id, count in Counter(issue_ids).items() if count > 1
    )
    if duplicates:
        errors.append(f"Duplicate picked AutoIssue IDs are not allowed: {_render_ids(duplicates)}.")
    return errors


def _resolved_counts(resolved_after: datetime | None) -> dict[str, int]:
    queryset = AutoIssue.objects.filter(
        status=AutoIssue.STATUS_RESOLVED,
        lessons_learned__gt="",
        resolved_at__isnull=False,
    )
    if resolved_after is not None:
        queryset = queryset.filter(resolved_at__gt=resolved_after)
    return dict(Counter(queryset.values_list("source", flat=True)))


def _available_issue_count(source: str, resolved_count: int) -> int:
    unresolved = (
        AutoIssue.objects.filter(source=source)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .count()
    )
    return unresolved + resolved_count


def _effective_requirement(source: str, configured_required: int, resolved_count: int) -> int:
    return min(configured_required, _available_issue_count(source, resolved_count))


def _mandatory_hard_errors(count: int, source: str, required: int) -> list[str]:
    effective_required = _effective_requirement(source, required, count)
    if count >= effective_required:
        return []
    short = effective_required - count
    suffix = f"{short} short; configured quota {required}"
    return [f"{source}: {count} of {effective_required} available resolved ({suffix})"]


def _hard_quota_errors(counts: dict[str, int]) -> list[str]:
    return _hard_quota_errors_scaled(
        counts, _HARD_SOURCE_REQUIREMENTS, _CROSS_SOURCE_REQUIREMENTS
    )


def _hard_quota_errors_scaled(
    counts: dict[str, int],
    hard_reqs: dict[str, int],
    cross_reqs: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    for source, required in hard_reqs.items():
        if required > 0:
            errors.extend(_mandatory_hard_errors(counts.get(source, 0), source, required))
    for source, required in cross_reqs.items():
        if required > 0:
            count = counts.get(source, 0)
            effective_required = _effective_requirement(source, required, count)
            if count < effective_required:
                errors.append(
                    f"{source}: {count} of {effective_required} available resolved "
                    f"({effective_required - count} short; configured quota {required})"
                )
    if errors:
        lighthouse_req = hard_reqs.get(AutoIssue.SOURCE_LIGHTHOUSE, 0)
        pg_stat_req = hard_reqs.get(AutoIssue.SOURCE_PG_STAT, 0)
        errors.append(
            f"Hard quota required: "
            f"{lighthouse_req} lighthouse, {pg_stat_req} pg_stat, "
            "and the configured source buckets."
        )
    return errors


def _missing_issue_errors(
    issue_ids: list[int], issues: dict[int, AutoIssue]
) -> list[str]:
    missing = [issue_id for issue_id in issue_ids if issue_id not in issues]
    if not missing:
        return []
    return [f"Picked AutoIssue IDs do not exist: {_render_ids(missing)}."]


def _duplicate_work_errors(
    issue_ids: list[int],
    issues: dict[int, AutoIssue],
) -> list[str]:
    by_key: dict[str, list[int]] = {}
    for issue_id in issue_ids:
        issue = issues.get(issue_id)
        if issue is None or not issue.canonical_fingerprint:
            continue
        by_key.setdefault(issue.canonical_fingerprint, []).append(issue_id)
    duplicate_groups = [ids for ids in by_key.values() if len(ids) > 1]
    if not duplicate_groups:
        return []
    rendered = "; ".join(_render_ids(ids) for ids in duplicate_groups)
    return [f"Duplicate picked AutoIssue work is not allowed: {rendered}."]


def _issue_state_errors(
    issue_ids: list[int],
    issues: dict[int, AutoIssue],
    resolved_after: datetime | None,
) -> list[str]:
    errors: list[str] = []
    for issue_id in issue_ids:
        issue = issues.get(issue_id)
        if issue is None:
            continue
        errors.extend(_single_issue_errors(issue, resolved_after))
    return errors


def _single_issue_errors(
    issue: AutoIssue, resolved_after: datetime | None
) -> list[str]:
    errors: list[str] = []
    if issue.status != AutoIssue.STATUS_RESOLVED:
        errors.append(f"#{issue.id} is {issue.status}, not resolved.")
    if issue.resolved_at is None:
        errors.append(f"#{issue.id} has no resolved_at time.")
    elif resolved_after and issue.resolved_at <= resolved_after:
        errors.append(f"#{issue.id} was resolved before the previous handoff.")
    if not issue.lessons_learned.strip():
        errors.append(f"#{issue.id} has no lessons_learned note.")
    return errors


def _render_ids(issue_ids: list[int]) -> str:
    return ", ".join(f"#{issue_id}" for issue_id in issue_ids)
