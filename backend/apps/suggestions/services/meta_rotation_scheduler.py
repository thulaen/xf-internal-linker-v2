"""
FR-225 Meta Rotation Scheduler.

Runs nightly via Celery beat. For each "single_active" stage slot it:
  1. Loads the last 30 days of HoldoutQuery rows for that slot.
  2. Skips if fewer than min_holdout_queries qualifying rows exist.
  3. Evaluates every alternate meta on the holdout set using NDCG@10.
  4. Promotes the winner if it beats the current champion by >= 1% NDCG.
  5. Persists results to MetaTournamentResult and updates WeightPreset.

For "all_active" slots there is no tournament — all members run sequentially
and this scheduler simply records a pass-through result.

RAM budget: <= 256 MB peak per meta evaluation.
Total for a 36-slot run: <= 512 MB (sequential, no concurrent shadow runs).
"""

import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.utils import timezone

from apps.core.models import AppSetting
from apps.suggestions.models import HoldoutQuery, MetaTournamentResult
from apps.suggestions.services.meta_slot_registry import (
    META_SLOT_REGISTRY,
    MetaSlotConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridden by AppSetting when available)
# ---------------------------------------------------------------------------
_DEFAULT_CADENCE_DAYS = 30
_DEFAULT_MIN_QUERIES = 100
_DEFAULT_PROMOTION_THRESHOLD_PCT = 1.0
_GRADE_WEIGHTS = {0: 0.0, 1: 1.0, 2: 2.0, 3: 3.0}  # relevance grades for NDCG


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


@dataclass
class TournamentResult:
    slot_id: str
    skipped: bool
    skip_reason: str = ""
    winner: str = ""
    previous_winner: str = ""
    ndcg_delta: Optional[float] = None
    promoted: bool = False
    results: list = None  # list of (meta_id, ndcg) tuples, best first

    def __post_init__(self):
        if self.results is None:
            self.results = []


def run_meta_tournament(slot_id: Optional[str] = None) -> list[TournamentResult]:
    """
    Run the tournament for all slots (or just one if slot_id is supplied).

    Returns a list of TournamentResult — one per slot processed.
    Call this directly for manual runs or from the Celery task.
    """
    if not _is_rotation_enabled():
        logger.info("meta_rotation.enabled is false — skipping tournament.")
        return []

    slots = (
        {slot_id: META_SLOT_REGISTRY[slot_id]}
        if slot_id and slot_id in META_SLOT_REGISTRY
        else META_SLOT_REGISTRY
    )

    outcomes = []
    for sid, config in slots.items():
        if config.pinned:
            logger.info("Slot %s is operator-pinned — skipping.", sid)
            outcomes.append(
                TournamentResult(
                    slot_id=sid, skipped=True, skip_reason="operator_pinned"
                )
            )
            continue

        if config.rotation_mode == "single_active":
            outcome = _run_single_active_tournament(sid, config)
        else:
            outcome = _run_all_active_pass(sid, config)

        outcomes.append(outcome)

    return outcomes


# ---------------------------------------------------------------------------
# Single-active tournament
# ---------------------------------------------------------------------------


def _run_single_active_tournament(
    slot_id: str, config: MetaSlotConfig
) -> TournamentResult:
    """Evaluate alternates on the holdout set and promote the best."""
    min_queries = _setting_int(
        "meta_rotation.min_holdout_queries", _DEFAULT_MIN_QUERIES
    )
    cadence_days = _setting_int(
        "meta_rotation.tournament_cadence_days", _DEFAULT_CADENCE_DAYS
    )
    threshold_pct = _setting_float(
        "meta_rotation.promotion_threshold_pct", _DEFAULT_PROMOTION_THRESHOLD_PCT
    )
    window_start = (timezone.now() - timedelta(days=cadence_days)).date()
    holdout_qs = HoldoutQuery.objects.filter(
        stage_slot=slot_id,
        window_start__gte=window_start,
        meets_min_impressions=True,
    )
    query_count = holdout_qs.count()
    if query_count < min_queries:
        logger.info(
            "Slot %s: only %d qualifying holdout rows (need %d) — skipping.",
            slot_id,
            query_count,
            min_queries,
        )
        return TournamentResult(
            slot_id=slot_id,
            skipped=True,
            skip_reason=f"insufficient_evidence ({query_count}/{min_queries})",
        )
    results = _evaluate_all_members(
        slot_id, config.members, list(holdout_qs), query_count
    )
    if not results:
        return TournamentResult(
            slot_id=slot_id, skipped=True, skip_reason="all_members_failed"
        )
    return _decide_and_persist(slot_id, config, results, query_count, threshold_pct)


def _evaluate_all_members(
    slot_id: str,
    members: list[str],
    holdout_rows: list,
    query_count: int,
) -> list[tuple[str, float]]:
    """Score every member meta on the holdout rows; skip crashed metas."""
    results = []
    now = timezone.now()
    for meta_id in members:
        try:
            ndcg = _evaluate_meta_on_holdout(meta_id, holdout_rows)
        except Exception as exc:
            logger.error("Meta %s crashed in slot %s: %s", meta_id, slot_id, exc)
            _record_result(
                slot_id=slot_id,
                meta_id=meta_id,
                ndcg=0.0,
                queries=query_count,
                was_winner=False,
                evaluated_at=now,
            )
            continue
        results.append((meta_id, ndcg))
        _record_result(
            slot_id=slot_id,
            meta_id=meta_id,
            ndcg=ndcg,
            queries=query_count,
            was_winner=False,
            evaluated_at=now,
        )
    return results


def _decide_and_persist(
    slot_id: str,
    config: MetaSlotConfig,
    results: list[tuple[str, float]],
    query_count: int,
    threshold_pct: float,
) -> TournamentResult:
    """Pick the winner, optionally promote, and return the outcome."""
    results.sort(key=lambda r: -r[1])
    best_meta, best_ndcg = results[0]
    current_winner = config.active_default
    current_ndcg = next((s for m, s in results if m == current_winner), 0.0)
    ndcg_delta = best_ndcg - current_ndcg
    now = timezone.now()
    promoted = False
    if _should_promote(current_winner, best_meta, ndcg_delta, threshold_pct):
        _promote_winner(
            slot_id,
            config,
            best_meta,
            current_winner,
            ndcg_delta,
            best_ndcg,
            query_count,
            now,
        )
        promoted = True
        logger.info(
            "Slot %s: promoted %s over %s (+%.4f NDCG@10, %d queries).",
            slot_id,
            best_meta,
            current_winner,
            ndcg_delta,
            query_count,
        )
    else:
        _update_winner_flag(slot_id, current_winner, now)
        logger.info(
            "Slot %s: current winner %s holds (challenger %s delta=%.4f < %.2f%%).",
            slot_id,
            current_winner,
            best_meta,
            ndcg_delta,
            threshold_pct,
        )
    return TournamentResult(
        slot_id=slot_id,
        skipped=False,
        winner=best_meta if promoted else current_winner,
        previous_winner=current_winner if promoted else "",
        ndcg_delta=ndcg_delta if promoted else None,
        promoted=promoted,
        results=results,
    )


def _run_all_active_pass(slot_id: str, config: MetaSlotConfig) -> TournamentResult:
    """No tournament for complementary slots — record a pass-through."""
    logger.debug("Slot %s is all_active — no tournament needed.", slot_id)
    return TournamentResult(
        slot_id=slot_id,
        skipped=False,
        winner="all",
        promoted=False,
        results=[(m, 1.0) for m in config.members],
    )


# ---------------------------------------------------------------------------
# NDCG@10 scoring
# ---------------------------------------------------------------------------


def _evaluate_meta_on_holdout(meta_id: str, holdout_rows: list[HoldoutQuery]) -> float:
    """
    Compute NDCG@10 for meta_id over the supplied holdout rows.

    Each HoldoutQuery row stores per_suggestion_data with ndcg_grade (0–3)
    and rank_position keyed by suggestion_id. We:
      1. Build the ideal DCG from the best possible ordering.
      2. Build the actual DCG from the positions the meta placed each suggestion.
      3. Average normalised DCG across all rows.

    Rows without per_suggestion_data for this meta are skipped.
    """
    ndcg_scores = []

    for row in holdout_rows:
        if not row.per_suggestion_data:
            continue

        # Collect (rank_position, ndcg_grade) tuples for suggestions in this row
        graded = []
        for suggestion_id, data in row.per_suggestion_data.items():
            grade = data.get("ndcg_grade", 0)
            rank = data.get("rank_position", 99)
            # Recency weight — recent impressions count more
            recency_weight = data.get("impression_recency_weight", 1.0)
            # IPS weight — correct for over-exposure of current winner
            ips_weight = data.get("ips_weight", 1.0)
            graded.append((rank, grade, recency_weight * ips_weight))

        if not graded:
            continue

        # Actual DCG: positions are 1-based, cap at rank 10
        actual_dcg = 0.0
        for rank, grade, weight in graded:
            if 1 <= rank <= 10:
                rel = _GRADE_WEIGHTS.get(grade, 0.0)
                actual_dcg += weight * rel / math.log2(rank + 1)

        # Ideal DCG: sort by grade descending, assign positions 1..N
        ideal_grades = sorted([g for _, g, _ in graded], reverse=True)[:10]
        ideal_dcg = sum(
            _GRADE_WEIGHTS.get(g, 0.0) / math.log2(pos + 2)
            for pos, g in enumerate(ideal_grades)
        )

        if ideal_dcg == 0.0:
            # All grades are 0 — no positive signal in this row
            continue

        ndcg_scores.append(actual_dcg / ideal_dcg)

    if not ndcg_scores:
        return 0.0

    return sum(ndcg_scores) / len(ndcg_scores)


# ---------------------------------------------------------------------------
# Promotion helpers
# ---------------------------------------------------------------------------


def _should_promote(
    current: str, candidate: str, ndcg_delta: float, threshold_pct: float
) -> bool:
    """Return True only if candidate strictly beats current by >= threshold_pct."""
    if candidate == current:
        return False  # no churn
    return (
        ndcg_delta >= threshold_pct * 0.01
    )  # threshold_pct is a percentage, e.g. 1.0 → 0.01


def _promote_winner(
    slot_id: str,
    config: MetaSlotConfig,
    new_winner: str,
    previous_winner: str,
    ndcg_delta: float,
    ndcg_score: float,
    queries: int,
    now,
) -> None:
    """Persist promotion: update in-memory registry + write MetaTournamentResult."""
    config.active_default = new_winner

    MetaTournamentResult.objects.filter(
        slot_id=slot_id, evaluated_at__date=now.date(), was_winner=True
    ).update(was_winner=False)

    MetaTournamentResult.objects.filter(
        slot_id=slot_id,
        meta_id=new_winner,
        evaluated_at__date=now.date(),
    ).update(was_winner=True, previous_winner=previous_winner, ndcg_delta=ndcg_delta)

    _emit_promotion_notification(
        slot_id, new_winner, previous_winner, ndcg_delta, queries
    )


def _update_winner_flag(slot_id: str, current_winner: str, now) -> None:
    """Mark the current winner as winner in today's results (no promotion)."""
    MetaTournamentResult.objects.filter(
        slot_id=slot_id,
        meta_id=current_winner,
        evaluated_at__date=now.date(),
    ).update(was_winner=True)


def _record_result(
    slot_id: str,
    meta_id: str,
    ndcg: float,
    queries: int,
    was_winner: bool,
    evaluated_at,
) -> None:
    """Upsert one MetaTournamentResult row."""
    MetaTournamentResult.objects.update_or_create(
        slot_id=slot_id,
        meta_id=meta_id,
        evaluated_at__date=evaluated_at.date(),
        defaults={
            "evaluated_at": evaluated_at,
            "ndcg_at_10": ndcg,
            "queries_evaluated": queries,
            "was_winner": was_winner,
        },
    )


def _emit_promotion_notification(
    slot_id: str, new_winner: str, previous_winner: str, delta: float, queries: int
) -> None:
    """Log a structured promotion event. Future: hook into notification system."""
    notify = _setting_bool("meta_rotation.notification_on_promotion", True)
    if notify:
        logger.warning(
            "META ROTATION PROMOTION | slot=%s | new=%s | old=%s | delta=+%.4f NDCG@10 | queries=%d",
            slot_id,
            new_winner,
            previous_winner,
            delta,
            queries,
        )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="suggestions.meta_rotation_tournament")
def meta_rotation_tournament(self, slot_id: Optional[str] = None):
    """
    Nightly Celery beat task — runs at 03:00 UTC.
    Evaluates all single_active slots against the last 30 days of holdout data.
    """
    logger.info("meta_rotation_tournament started (slot_id=%s).", slot_id or "ALL")
    outcomes = run_meta_tournament(slot_id=slot_id)
    promoted = [o for o in outcomes if o.promoted]
    skipped = [o for o in outcomes if o.skipped]
    logger.info(
        "meta_rotation_tournament finished: %d slots evaluated, %d promoted, %d skipped.",
        len(outcomes),
        len(promoted),
        len(skipped),
    )
    return {
        "slots_evaluated": len(outcomes),
        "promotions": [
            {"slot": o.slot_id, "winner": o.winner, "delta": o.ndcg_delta}
            for o in promoted
        ],
        "skipped": [{"slot": o.slot_id, "reason": o.skip_reason} for o in skipped],
    }


# ---------------------------------------------------------------------------
# AppSetting helpers
# ---------------------------------------------------------------------------


def _is_rotation_enabled() -> bool:
    return _setting_bool("meta_rotation.enabled", True)


def _setting_int(key: str, default: int) -> int:
    try:
        return int(AppSetting.objects.get(key=key).value)
    except (AppSetting.DoesNotExist, ValueError):
        return default


def _setting_float(key: str, default: float) -> float:
    try:
        return float(AppSetting.objects.get(key=key).value)
    except (AppSetting.DoesNotExist, ValueError):
        return default


def _setting_bool(key: str, default: bool) -> bool:
    try:
        val = AppSetting.objects.get(key=key).value.strip().lower()
        return val in ("true", "1", "yes")
    except AppSetting.DoesNotExist:
        return default
