"""Phase 4.3 — Confidence Meter for "Ready to Rock" status.

Returns a single readiness score 0-100 aggregating seven contributors:

    1. Content imported (10 pts) — at least one ContentItem exists
    2. Embeddings fresh (20 pts) — % at current model version
    3. C++ loaded (20 pts) — % of native kernels on cpp runtime path
    4. No duplicate pile-up (15 pts) — dedup invariant audit clean
    5. Migrations clean (10 pts) — no unmigrated changes detected
    6. Frontend built (5 pts) — xf-linker-frontend-prod image present
    7. Open issues known (20 pts) — operator has acknowledged or
       resolved every unresolved ErrorLog row

Total = 100. Operator sees a single big chip on the Dashboard plus a
drill-down listing each contributor's score + plain-English fix hint
when below max.

Storage discipline: results cached in Redis with 60-second TTL. No
new tables — every contributor reads existing models via cheap
indexed queries.

Citations: NPS-style aggregator pattern (Reichheld 2003 HBR). Per-check
weight is heuristic; operator can audit by reading the breakdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


CACHE_KEY = "confidence_meter.snapshot"
CACHE_TTL_SECONDS = 60

# Phase 4 fix #3 — embedding signature cached as a single AppSetting row.
# The embed pipeline writes this key the first time it loads the model
# in a worker process (apps.pipeline.services.embeddings.publish_current_embedding_signature).
# Reading it on the dashboard hot-path avoids a cold model load.
APP_SETTING_EMBEDDING_SIGNATURE = "embedding.current_signature"


def _read_cached_embedding_signature() -> str:
    """Return the BGE-M3 signature from the AppSetting cache, or "" if unset.

    Never loads the model. The embed pipeline writes this key on its
    first encode op per worker process. If no worker has run yet, the
    Confidence Meter treats freshness as "match by row presence" rather
    than blocking on a cold load.
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=APP_SETTING_EMBEDDING_SIGNATURE).first()
        if row and row.value:
            return str(row.value).strip()
    except Exception:
        logger.debug(
            "confidence_meter: embedding signature cache read failed", exc_info=True
        )
    return ""


@dataclass(frozen=True)
class ContributorResult:
    """One contributor's contribution to the readiness score."""

    name: str
    label: str
    score: float  # 0-1 scale per contributor (gets multiplied by max_pts)
    max_pts: int
    fix_hint: str = ""

    @property
    def points(self) -> float:
        return self.score * self.max_pts


@dataclass(frozen=True)
class ConfidenceSnapshot:
    """Whole-system readiness summary."""

    total: float  # 0-100
    label: str  # "Ready to rock" | "Mostly ready" | "Issues" | "Needs setup"
    contributors: list[ContributorResult] = field(default_factory=list)


def get_confidence_snapshot(force_refresh: bool = False) -> ConfidenceSnapshot:
    """Compute (or read from cache) the current readiness snapshot."""
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

    contributors = [
        _check_content_imported(),
        _check_embeddings_fresh(),
        _check_cpp_loaded(),
        _check_dedup_clean(),
        _check_migrations_clean(),
        _check_frontend_built(),
        _check_errors_acknowledged(),
        # Phase 4.6.10 / 4.9 — helper-PC contributor. Adds visibility
        # for whether the operator's helper PCs (if any) are healthy
        # and accepting work. Default 5 pts; reduces _check_errors
        # max_pts from 20 to 15 inside that helper to keep the total
        # at 100 — see _check_errors_acknowledged().
        _check_helpers_healthy(),
    ]

    total = sum(c.points for c in contributors)
    label = _label_for(total)
    snapshot = ConfidenceSnapshot(total=round(total, 1), label=label, contributors=contributors)
    cache.set(CACHE_KEY, snapshot, CACHE_TTL_SECONDS)
    return snapshot


def _label_for(total: float) -> str:
    if total >= 90:
        return "Ready to rock"
    if total >= 70:
        return "Mostly ready"
    if total >= 40:
        return "Issues — review breakdown"
    return "Needs setup"


# ── Per-contributor checks ────────────────────────────────────────


def _check_content_imported() -> ContributorResult:
    """10 pts: at least one non-deleted ContentItem exists."""
    try:
        from apps.content.models import ContentItem

        exists = ContentItem.objects.filter(is_deleted=False).exists()
        return ContributorResult(
            name="content_imported",
            label="Content imported",
            score=1.0 if exists else 0.0,
            max_pts=10,
            fix_hint="" if exists else "Run an import from /admin/sync to bring in your first content.",
        )
    except Exception:
        logger.debug("confidence_meter: content_imported check failed", exc_info=True)
        return ContributorResult(
            name="content_imported",
            label="Content imported",
            score=0.0,
            max_pts=10,
            fix_hint="ContentItem table unavailable — run migrations.",
        )


def _check_embeddings_fresh() -> ContributorResult:
    """20 pts: fraction of ContentItems whose embedding matches the current model version.

    Phase 4 fix #3 — read the BGE-M3 signature from a cached AppSetting
    row (key ``embedding.current_signature``) instead of loading the
    model on every dashboard refresh. The cache is populated by the
    embed pipeline (which already loads the model for real work) and
    refreshed weekly by the existing ``embedding_audit`` Celery task.
    Cold dashboards now respond instantly rather than blocking on a
    ~10 s model load.
    """
    try:
        from apps.content.models import ContentItem

        signature = _read_cached_embedding_signature()

        total = ContentItem.objects.filter(is_deleted=False, duplicate_of__isnull=True).count()
        if total == 0:
            # No content yet → freshness is N/A; full pts so we don't penalise a fresh install.
            return ContributorResult(
                name="embeddings_fresh",
                label="Embeddings fresh",
                score=1.0,
                max_pts=20,
            )
        if signature:
            fresh = ContentItem.objects.filter(
                is_deleted=False,
                duplicate_of__isnull=True,
                embedding__isnull=False,
                embedding_model_version=signature,
            ).count()
        else:
            fresh = ContentItem.objects.filter(
                is_deleted=False,
                duplicate_of__isnull=True,
                embedding__isnull=False,
            ).count()
        ratio = fresh / max(total, 1)
        hint = ""
        if ratio < 0.95:
            stale = total - fresh
            hint = f"{stale} items have stale embeddings — run pipeline.reembed_null_embeddings."
        return ContributorResult(
            name="embeddings_fresh",
            label="Embeddings fresh",
            score=min(1.0, max(0.0, ratio)),
            max_pts=20,
            fix_hint=hint,
        )
    except Exception:
        logger.debug("confidence_meter: embeddings_fresh check failed", exc_info=True)
        return ContributorResult(
            name="embeddings_fresh",
            label="Embeddings fresh",
            score=0.0,
            max_pts=20,
            fix_hint="Could not query embedding signature — see /error-log.",
        )


def _check_cpp_loaded() -> ContributorResult:
    """20 pts: fraction of native kernels currently on the cpp runtime path."""
    try:
        from apps.diagnostics.health import _native_module_runtime_status

        statuses = _native_module_runtime_status()
        total = len(statuses)
        if total == 0:
            return ContributorResult(
                name="cpp_loaded",
                label="C++ kernels loaded",
                score=0.0,
                max_pts=20,
                fix_hint="No native kernels registered — check apps.diagnostics.health.",
            )
        on_cpp = sum(1 for s in statuses if s.get("runtime_path") == "cpp")
        ratio = on_cpp / total
        hint = ""
        if ratio < 1.0:
            fallback = [s.get("label") or s.get("module") for s in statuses if s.get("fallback_active")]
            hint = f"On Python fallback: {', '.join(fallback)}. Rebuild via 'docker compose build backend'."
        return ContributorResult(
            name="cpp_loaded",
            label="C++ kernels loaded",
            score=ratio,
            max_pts=20,
            fix_hint=hint,
        )
    except Exception:
        logger.debug("confidence_meter: cpp_loaded check failed", exc_info=True)
        return ContributorResult(
            name="cpp_loaded",
            label="C++ kernels loaded",
            score=0.0,
            max_pts=20,
            fix_hint="Could not query native module statuses.",
        )


def _check_dedup_clean() -> ContributorResult:
    """15 pts: dedup invariant audit reports zero violations."""
    try:
        from apps.core.services.self_test_smoke import run_startup_smoke_tests

        warnings = run_startup_smoke_tests()
        clean = len(warnings) == 0
        return ContributorResult(
            name="dedup_clean",
            label="No duplicate pile-up",
            score=1.0 if clean else 0.0,
            max_pts=15,
            fix_hint="" if clean else f"{len(warnings)} table(s) violate NO-DUPLICATES.md — see /diagnostics.",
        )
    except Exception:
        logger.debug("confidence_meter: dedup_clean check failed", exc_info=True)
        return ContributorResult(
            name="dedup_clean",
            label="No duplicate pile-up",
            score=0.5,
            max_pts=15,
            fix_hint="Audit could not run.",
        )


def _check_migrations_clean() -> ContributorResult:
    """10 pts: no schema model is ahead of the applied migrations."""
    try:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command(
                "makemigrations",
                "--check",
                "--dry-run",
                stdout=out,
                stderr=out,
                verbosity=0,
            )
            clean = True
        except SystemExit:
            # makemigrations --check exits non-zero if changes would be created.
            clean = False
        return ContributorResult(
            name="migrations_clean",
            label="Migrations clean",
            score=1.0 if clean else 0.0,
            max_pts=10,
            fix_hint=""
            if clean
            else "A model has changed without a migration — run 'manage.py makemigrations'.",
        )
    except Exception:
        logger.debug("confidence_meter: migrations_clean check failed", exc_info=True)
        return ContributorResult(
            name="migrations_clean",
            label="Migrations clean",
            score=0.5,
            max_pts=10,
            fix_hint="makemigrations check could not run.",
        )


def _check_frontend_built() -> ContributorResult:
    """5 pts: the frontend prod image exists.

    This is a weak signal (we can't ask Docker from inside the backend
    container reliably), so we infer via the existence of the static
    bundle directory under /app/static (which the frontend image places
    there during the build).
    """
    try:
        from pathlib import Path

        from django.conf import settings

        bundle_root = Path(getattr(settings, "STATIC_ROOT", "/app/static"))
        # Static index.html is the entry point the nginx upstream reads.
        index_present = bundle_root.joinpath("index.html").exists()
        return ContributorResult(
            name="frontend_built",
            label="Frontend built",
            score=1.0 if index_present else 0.0,
            max_pts=5,
            fix_hint=""
            if index_present
            else "Run 'docker compose build frontend-build' to rebuild the production bundle.",
        )
    except Exception:
        logger.debug("confidence_meter: frontend_built check failed", exc_info=True)
        return ContributorResult(
            name="frontend_built",
            label="Frontend built",
            score=0.5,
            max_pts=5,
        )


def _check_errors_acknowledged() -> ContributorResult:
    """15 pts (was 20; reduced 2026-05-02 to make room for the new
    helpers contributor — total still adds to 100): every unresolved
    ErrorLog has been acknowledged.

    Plain-English: an unack'd error means the operator hasn't seen and
    accepted (or fixed) it yet. The contributor scales linearly: 0 unack
    rows = full marks; ≥10 unack rows = zero marks.
    """
    try:
        from apps.audit.models import ErrorLog

        unack = ErrorLog.objects.filter(acknowledged=False).count()
        # Linear ramp from 1.0 (zero unack) → 0.0 (10+ unack).
        score = max(0.0, 1.0 - (unack / 10.0))
        hint = ""
        if unack > 0:
            hint = f"{unack} unacknowledged error(s) — review /error-log."
        return ContributorResult(
            name="errors_acknowledged",
            label="Errors acknowledged",
            score=score,
            max_pts=15,
            fix_hint=hint,
        )
    except Exception:
        logger.debug("confidence_meter: errors_acknowledged check failed", exc_info=True)
        return ContributorResult(
            name="errors_acknowledged",
            label="Errors acknowledged",
            score=0.5,
            max_pts=15,
        )


def _check_helpers_healthy() -> ContributorResult:
    """Phase 4.6.10 / 4.9 — 5 pts: helper PCs are healthy and accepting work.

    Reads from the cached helper roster. Scoring rules:
        * No helpers configured        → 1.0 (full marks; not all
                                         operators have a 2nd PC; we
                                         don't penalise that case).
        * 1+ helpers, all accepting    → 1.0
        * 1+ helpers, some not         → 0.7
        * 1+ helpers, none accepting   → 0.3
        * Helpers configured but offline → 0.0 (with hint)

    Storage discipline: roster() is cache-backed (60 s TTL); zero new
    queries on the dashboard hot path.
    """
    try:
        from apps.core.helpers import roster

        score, hint = _score_helpers_state(roster())
    except Exception:
        logger.debug("confidence_meter: helpers_healthy check failed", exc_info=True)
        score, hint = 0.5, ""
    return ContributorResult(
        name="helpers_healthy",
        label="Helper PCs healthy",
        score=score,
        max_pts=5,
        fix_hint=hint,
    )


def _score_helpers_state(snap) -> tuple[float, str]:
    """Map a roster snapshot to a (score, fix_hint) pair. Pure function — testable."""
    total_configured = len(snap.helpers)
    if total_configured == 0:
        return 1.0, ""
    if snap.online_count == 0:
        return 0.0, (
            f"{total_configured} helper(s) configured but none online — "
            "check helper docker compose + network connectivity."
        )
    if snap.accepting_work_count == 0:
        return 0.3, (
            f"{snap.online_count} helper(s) online but none accepting work — "
            "toggle 'Accept work' on /settings/helpers."
        )
    accepting_ratio = snap.accepting_work_count / max(total_configured, 1)
    if accepting_ratio >= 1.0:
        return 1.0, ""
    return 0.7, (
        f"{snap.accepting_work_count} of {total_configured} helper(s) accepting work — "
        "review /settings/helpers."
    )
