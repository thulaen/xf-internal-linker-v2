"""Feedback-driven destination relevance — picks #33 + #34 wiring.

Two complementary signals from operator review history:

1. **Cascade Click Model (pick #34)** — given a ranked list of
   destinations shown together with one approved → that approved
   destination is the click; the destinations above it (which the
   reviewer also examined) become "skipped" evidence.
2. **Position-bias IPS (pick #33)** — even with cascade semantics,
   destinations consistently appearing near the top get more
   approvals just because they were shown more prominently. IPS
   weights down those exposure-bias gains.

Per-destination relevance is persisted to AppSetting so:

- The review-queue ranker can read it as a feedback feature.
- The `cascade_click_em_re_estimate` and `position_bias_ips_refit`
  scheduled jobs (W1) drop their smoke-test bodies and call into
  this module instead.

Same pattern as :mod:`apps.pipeline.services.score_calibrator`:

- :func:`load_relevance_table` returns the persisted dict
  ``{destination_pk: relevance}`` (cold start: ``{}``).
- :func:`compute_and_persist` rebuilds from recent Suggestion
  history and writes back via ``AppSetting``.

The persisted JSON stays well under the 64 KB practical AppSetting
ceiling: at ~12 bytes per entry that's room for ~5000 destinations,
well above the ~1000-suggestion review pool we typically work with.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from .cascade_click_model import ClickSession, estimate as cascade_estimate
from .position_bias_ips import DEFAULT_MAX_WEIGHT, ips_weight

logger = logging.getLogger(__name__)


KEY_CASCADE_RELEVANCE = "feedback_relevance.cascade.json"
KEY_IPS_CTR = "feedback_relevance.ips.json"
KEY_FITTED_AT = "feedback_relevance.fitted_at"
KEY_TRAINING_RUNS = "feedback_relevance.training_runs"

#: Lookback window for the weekly aggregation. Long enough to absorb
#: review-cadence noise, short enough to stay current with operator
#: drift.
DEFAULT_LOOKBACK_DAYS: int = 60

#: Minimum pipeline runs needed before the aggregation is meaningful.
#: Cascade with one observation per destination is unstable.
MIN_PIPELINE_RUNS: int = 5


@dataclass(frozen=True)
class FeedbackSnapshot:
    """Per-destination feedback aggregates."""

    cascade_relevance: dict[int, float]
    ips_weighted_ctr: dict[int, float]
    fitted_at: str | None
    training_runs: int


# ── Read API ──────────────────────────────────────────────────────


def load_snapshot() -> FeedbackSnapshot | None:
    """Return the persisted aggregates, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None

    rows = dict(
        AppSetting.objects.filter(
            key__in=[
                KEY_CASCADE_RELEVANCE,
                KEY_IPS_CTR,
                KEY_FITTED_AT,
                KEY_TRAINING_RUNS,
            ]
        ).values_list("key", "value")
    )
    if KEY_CASCADE_RELEVANCE not in rows:
        return None
    try:
        cascade_raw = json.loads(rows.get(KEY_CASCADE_RELEVANCE) or "{}")
        ips_raw = json.loads(rows.get(KEY_IPS_CTR) or "{}")
        runs = int(rows.get(KEY_TRAINING_RUNS, "0") or "0")
    except (TypeError, ValueError):
        logger.warning(
            "feedback_relevance: malformed AppSetting JSON, ignoring snapshot"
        )
        return None
    return FeedbackSnapshot(
        cascade_relevance={int(k): float(v) for k, v in cascade_raw.items()},
        ips_weighted_ctr={int(k): float(v) for k, v in ips_raw.items()},
        fitted_at=rows.get(KEY_FITTED_AT),
        training_runs=runs,
    )


def cascade_relevance_for(destination_pk: int) -> float:
    """Return the Cascade-estimated relevance for *destination_pk*.

    Two-source resolution (Group A.4 wiring):

    1. **Preferred — impression-based** (``cascade_click_em_producer``).
       Real cascade EM on per-viewport-impression click data. Empty
       until the frontend hook lands and impressions accumulate.
    2. **Fallback — review-queue based** (this module's ``compute_and_persist``).
       Always-on data: each pipeline_run becomes one cascade session
       built from operator approvals.
    3. **Final fallback** — neutral 0.5 (the prior mean ``α / (α+β)``).

    Cold-start safe at every layer: empty AppSetting → neutral 0.5,
    same convention used elsewhere for missing-data feedback fields.
    """
    # Delay-import to avoid producer↔consumer cycles at module load.
    from .cascade_click_em_producer import (
        load_relevance_table as load_impression_table,
    )

    impression_table = load_impression_table()
    if impression_table:
        # Impression-based table populated → use it.
        if int(destination_pk) in impression_table:
            return impression_table[int(destination_pk)]
        # Impression-based exists but doesn't have this dest → fall
        # through to the review-queue table rather than returning 0.5
        # straight away. Combining the two sources is the most
        # information-rich answer.

    snap = load_snapshot()
    if snap is None:
        return 0.5
    return snap.cascade_relevance.get(int(destination_pk), 0.5)


# ── Write API ────────────────────────────────────────────────────


def compute_and_persist(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_runs: int = MIN_PIPELINE_RUNS,
) -> FeedbackSnapshot | None:
    """Rebuild and persist the aggregates.

    Builds Cascade sessions from past pipeline runs (one session per
    run, ranked-docs = the run's pending+approved+rejected suggestions
    ordered by composite score, click = the lowest-rank approved).
    Runs `cascade_click_model.estimate` and computes per-destination
    IPS-weighted CTR.
    """
    from django.utils import timezone

    sessions, position_events = _build_observations(lookback_days=lookback_days)
    if len(sessions) < min_runs:
        logger.info(
            "feedback_relevance: only %d / %d runs available — skip persist",
            len(sessions),
            min_runs,
        )
        return None

    cascade_table = cascade_estimate(sessions)
    cascade_relevance = {
        int(doc_id): float(rel.relevance)
        for doc_id, rel in cascade_table.items()
        if isinstance(doc_id, (int, str)) and str(doc_id).lstrip("-").isdigit()
    }

    ips_ctr = _compute_ips_ctr(position_events)

    snapshot = _persist(
        cascade=cascade_relevance,
        ips=ips_ctr,
        runs=len(sessions),
        fitted_at=timezone.now().isoformat(),
    )
    logger.info(
        "feedback_relevance: persisted (cascade=%d entries, ips=%d entries, "
        "runs=%d)",
        len(cascade_relevance),
        len(ips_ctr),
        len(sessions),
    )
    return snapshot


# ── Internals ────────────────────────────────────────────────────


def _build_observations(
    *, lookback_days: int
) -> tuple[list[ClickSession], dict[int, list[bool]]]:
    """Return ``(cascade_sessions, position → [was_approved, ...])``.

    ``position_events`` maps a 1-based display rank to the list of
    approved/rejected outcomes the operator gave to suggestions
    shown at that rank. Used by the IPS aggregation.
    """
    from django.utils import timezone

    try:
        from apps.suggestions.models import PipelineRun, Suggestion
    except Exception:  # pragma: no cover
        return [], {}

    cutoff = timezone.now() - timedelta(days=lookback_days)
    runs_with_suggestions = list(
        PipelineRun.objects.filter(created_at__gte=cutoff).values_list("pk", flat=True)
    )

    sessions: list[ClickSession] = []
    position_events: dict[int, list[bool]] = defaultdict(list)
    for run_pk in runs_with_suggestions:
        rows = list(
            Suggestion.objects.filter(pipeline_run_id=run_pk)
            .filter(status__in=["approved", "rejected", "pending"])
            .order_by("-score_semantic")
            .values("destination_id", "status")
        )
        if not rows:
            continue
        ranked_docs: list[int] = [int(r["destination_id"]) for r in rows]
        clicked_rank: int | None = None
        for idx, row in enumerate(rows, start=1):
            if row["status"] == "approved" and clicked_rank is None:
                clicked_rank = idx
            position_events[idx].append(row["status"] == "approved")
        sessions.append(
            ClickSession(ranked_docs=ranked_docs, clicked_rank=clicked_rank)
        )
    return sessions, dict(position_events)


def _compute_ips_ctr(position_events: dict[int, list[bool]]) -> dict[int, float]:
    """Return per-position IPS-weighted CTR.

    Group A.4 wiring: ``η`` is read from
    ``position_bias_ips_producer.load_eta()`` so the IPS weights use
    the data-fit power-law exponent when impression data has trained
    one. Cold-start safe: ``load_eta()`` returns
    ``DEFAULT_POWER_LAW_ETA = 1.0`` when no fit is persisted yet, so
    this function's behaviour is identical to the pre-A.4 hardcoded
    path until the producer's first successful fit lands.

    Result keyed by 1-based position, value in roughly the unit
    interval (could exceed 1 when a deep position has many approvals
    and the IPS weight expands them — caller is free to clip).
    """
    # Delay-import to avoid producer↔consumer cycles at module load.
    from .position_bias_ips_producer import load_eta

    eta = load_eta()
    out: dict[int, float] = {}
    for position, events in position_events.items():
        if not events:
            continue
        approvals = sum(1 for e in events if e)
        weight = ips_weight(
            position=position,
            eta=eta,
            max_weight=DEFAULT_MAX_WEIGHT,
        )
        out[position] = (approvals / len(events)) * weight
    return out


def _persist(
    *,
    cascade: dict[int, float],
    ips: dict[int, float],
    runs: int,
    fitted_at: str,
) -> FeedbackSnapshot:
    from apps.core.models import AppSetting

    AppSetting.objects.update_or_create(
        key=KEY_CASCADE_RELEVANCE,
        defaults={
            "value": json.dumps(
                {str(k): v for k, v in cascade.items()},
                separators=(",", ":"),
            ),
            "description": (
                "Per-destination Cascade-model relevance estimate "
                "(pick #34). Refit weekly by cascade_click_em_re_estimate."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_IPS_CTR,
        defaults={
            "value": json.dumps(
                {str(k): v for k, v in ips.items()},
                separators=(",", ":"),
            ),
            "description": (
                "Per-position IPS-weighted CTR (pick #33). "
                "Refit weekly by position_bias_ips_refit."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_FITTED_AT,
        defaults={
            "value": fitted_at,
            "description": "Timestamp of the last feedback_relevance refit.",
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_TRAINING_RUNS,
        defaults={
            "value": str(runs),
            "description": "Number of PipelineRun rows in the last training set.",
        },
    )
    return FeedbackSnapshot(
        cascade_relevance=cascade,
        ips_weighted_ctr=ips,
        fitted_at=fitted_at,
        training_runs=runs,
    )
