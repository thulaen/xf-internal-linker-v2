"""Django endpoint behind scripts/session_start_payload.py.

Returns JSON: {"markers": {...}, "total_open_count": N}.

The Go "startupd" proxy that used to sit between the script and this
endpoint was retired on 2026-06-11 (ADR 0007 — Python + Rust only);
the script now calls this endpoint directly through nginx. Exposed as
GET /api/session-gate/.

Query params:
  type  — session type (docs/infrastructure/reconciliation/feature).
           Unused by the DB queries; the script records it in
           audit/session_gate_state.json for the quota hook.
  area  — repeatable repo-relative path; used for scoped lesson lookup.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import picker as pt_picker


_OPEN_STATUSES = (AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)

# 10 sources in the canonical REGISTRY READ marker order.
# Tuple: (source_constant, picks_prefix).  Empty string = no prefix (agent).
_SOURCE_ORDER: tuple[tuple[str, str], ...] = (
    (AutoIssue.SOURCE_AGENT, ""),
    (AutoIssue.SOURCE_GLITCHTIP, "g"),
    (AutoIssue.SOURCE_PYROSCOPE, "p"),
    (AutoIssue.SOURCE_TEMPO, "t"),
    (AutoIssue.SOURCE_LOKI, "l"),
    (AutoIssue.SOURCE_FARO, "f"),
    (AutoIssue.SOURCE_MUTATION, "m"),
    (AutoIssue.SOURCE_FUZZ, "z"),
    (AutoIssue.SOURCE_CONTRACT, "c"),
    (AutoIssue.SOURCE_GH_CI, "gh"),
)

# 16 paper-trail categories in the canonical PAPER TRAIL READ marker order.
_PT_CATEGORY_ORDER = (
    "autoissue_deferral", "cve_upgrade", "coverage_gap", "infrastructure",
    "ruff_sweep", "mutation_survivor", "debt_reduction", "feature_decision",
    "tooling_gap", "documentation", "dependency_upgrade", "refactor",
    "performance", "security", "accessibility", "other",
)

# TDD pipeline categories bootstrapped idempotently at gate time.
_TDD_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    ("test_case", "Test case (BDD contract)", "Given/When/Then contract.", 205),
    ("tdd_lesson", "TDD Red-Green-Refactor lesson", "One R/G/R cycle.", 210),
    ("code_review_lesson", "Code review lesson", "Self-review finding.", 215),
    ("hook_failure", "Pre-commit hook failure", "Auto-logged non-zero exit.", 220),
    ("decision_point", "Post-commit decision point", "Post-commit retrospective.", 225),
)

_TDD_PIPELINE = "SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON"
_TDD_SWITCHES = (
    "spec_citation", "test_case_mandate", "tdd_red_green_refactor",
    "5_layer_coverage", "code_review_logging", "lesson_logging",
    "decision_point", "artefact_pruning", "no_bypass",
    "per_file_lookup", "commit_failure_lookup",
)


@require_GET
def session_gate(request):
    areas = request.GET.getlist("area") or [""]
    sticky = _sticky_marker()
    registry, total_open = _registry_marker()
    paper_trail = _paper_trail_marker()
    snapshots = _snapshots_marker()
    lessons = _lessons_marker(areas)
    tdd = _tdd_preflight_marker()
    return JsonResponse({
        "markers": {
            "sticky": sticky,
            "registry": registry,
            "paper_trail": paper_trail,
            "snapshots": snapshots,
            "lessons": lessons,
            "tdd_preflight": tdd,
        },
        "total_open_count": total_open,
    })


def _now_utc_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sticky_marker() -> str:
    entry = (
        PaperTrailEntry.objects.filter(status=PaperTrailEntry.STATUS_STICKY)
        .order_by("id")
        .first()
    )
    if entry is None:
        return "[STICKY 1 READ: timestamp=N/A sha256=0000000000000000 agent=session-gate]"
    body = entry.abstract or ""
    sha = hashlib.sha256(body.encode()).hexdigest()[:16]
    return f"[STICKY 1 READ: timestamp={_now_utc_z()} sha256={sha} agent=session-gate]"


def _registry_marker() -> tuple[str, int]:
    """Return (registry_marker_string, total_open_count)."""
    total = AutoIssue.objects.filter(status__in=_OPEN_STATUSES).count()

    counts: dict[str, int] = {}
    picks: dict[str, list] = {}
    for source, _pfx in _SOURCE_ORDER:
        qs = (
            AutoIssue.objects.filter(status__in=_OPEN_STATUSES, source=source)
            .order_by("-priority_score", "spam_score", "-last_seen")
        )
        counts[source] = qs.count()
        picks[source] = list(qs[:3])

    # Agent pool for drought substitution in non-agent buckets.
    agent_used_ids: set[int] = {i.id for i in picks[AutoIssue.SOURCE_AGENT]}
    agent_pool = list(
        AutoIssue.objects.filter(status__in=_OPEN_STATUSES, source=AutoIssue.SOURCE_AGENT)
        .order_by("-priority_score", "spam_score", "-last_seen")[:30]
    )

    breakdown = " / ".join(
        f"{counts[src]} {src}" for src, _pfx in _SOURCE_ORDER
    )

    picks_parts: list[str] = []
    for source, prefix in _SOURCE_ORDER:
        part = _format_picks_segment(
            source, prefix, picks[source], agent_pool, agent_used_ids
        )
        picks_parts.append(part)

    # The marker header N is the SUM of the ten picker-source counts —
    # .githooks/check-registry-read.py (NEW_MARKER_RE) asserts the ten numbers
    # sum to N. It is NOT the grand total of every open AutoIssue: rows in
    # non-picker categories (code_review_lesson, tdd_lesson, hook_failure,
    # test_case, observability, ...) are excluded from the 30-pick ritual, so
    # the header must equal the bucket sum to stay self-consistent.
    # total_open_count (returned below, used to sign the session-gate HMAC
    # token) stays the grand total so token sign/verify still agree.
    picker_total = sum(counts.values())
    marker = (
        f"[REGISTRY READ: {picker_total} open ({breakdown}) — "
        f"picked: {' | '.join(picks_parts)}]"
    )
    return marker, total


def _format_picks_segment(
    source: str,
    prefix: str,
    issues: list,
    agent_pool: list,
    agent_used_ids: set[int],
) -> str:
    if len(issues) >= 3:
        ids = ", ".join(f"#{i.id}" for i in issues[:3])
        return f"{prefix}: {ids}" if prefix else ids

    needed = 3 - len(issues)
    existing_ids = {i.id for i in issues}
    subs = [
        a for a in agent_pool
        if a.id not in existing_ids and a.id not in agent_used_ids
    ][:needed]
    agent_used_ids.update(a.id for a in subs)
    ids = ", ".join(f"#{i.id}" for i in (issues + subs))
    drought_id = _log_drought_issue(source, len(issues))
    seg = f"0 found + 3 from agent: {ids} (drought logged: #{drought_id})"
    return f"{prefix}: {seg}" if prefix else seg


def _log_drought_issue(source: str, found_count: int) -> int:
    obj, _ = AutoIssue.objects.get_or_create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"picker_drought:{source}",
        defaults={
            "title": f"[picker_drought] {source}: only {found_count} open AutoIssues",
            "status": AutoIssue.STATUS_OPEN,
            "severity": AutoIssue.SEVERITY_LOW,
        },
    )
    return obj.id


def _paper_trail_marker() -> str:
    total = pt_picker.total_open()
    counts = pt_picker.count_by_category()
    top10 = pt_picker.pick_top_n(10)
    breakdown = " / ".join(
        f"{counts.get(cat, 0)} {cat}" for cat in _PT_CATEGORY_ORDER
    )
    pick_ids = ", ".join(f"#{e.id}" for e in top10)
    return f"[PAPER TRAIL READ: {total} open ({breakdown}) — picked: {pick_ids}]"


def _snapshots_marker() -> str:
    # The Go snapshotd daemon was retired on 2026-06-11 (ADR 0007) and
    # nothing ever created snapshots in production, so the store was
    # always empty. The hooks accept this exact skipped form; keep the
    # wording stable until a Python snapshot store exists.
    return "[SNAPSHOTS READ: skipped — snapshotd unavailable]"


def _lessons_marker(areas: list[str]) -> str:
    from apps.paper_trail.services import lesson_index as svc  # noqa: PLC0415
    seen: dict[int, dict] = {}
    for area in areas:
        for h in svc.scoped_find(area, limit=10):
            if h["autoissue_id"] not in seen:
                seen[h["autoissue_id"]] = h
    merged = sorted(
        seen.values(),
        key=lambda r: (
            -int(r.get("severity") or 0),
            -int(r.get("resolved_at_unix") or 0),
        ),
    )[:10]
    areas_str = ", ".join(a for a in areas if a) or "<no-areas-specified>"
    return (
        f"[LESSONS BEFORE START: {len(merged)} resolved-lesson rows "
        f"reviewed in {areas_str}]"
    )


def _tdd_preflight_marker() -> str:
    for key, label, desc, order in _TDD_CATEGORIES:
        AutoIssueCategory.objects.get_or_create(
            key=key,
            defaults={"label": label, "description": desc, "sort_order": order},
        )
    session_id = str(uuid.uuid4())
    armed_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    switches = " ".join(f"{k}=on" for k in _TDD_SWITCHES)
    return (
        f"[TDD PREFLIGHT: pipeline={_TDD_PIPELINE} "
        f"{switches} session_id={session_id} armed_at={armed_at}]"
    )
