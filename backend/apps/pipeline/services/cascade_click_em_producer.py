"""Producer + read API for pick #34 Cascade Click Model.

The math helper at :mod:`apps.pipeline.services.cascade_click_model`
takes ``ClickSession`` objects and returns per-doc Cascade
relevance via the standard MLE-with-Laplace estimator. This module
is the producer side: read the ``SuggestionImpression`` log, build
sessions, run the EM estimator, persist results to AppSetting.

This is a sibling of
:mod:`apps.pipeline.services.position_bias_ips_producer` and shares
its design contract:

- **Cold-start safe.** Until the frontend hook lands and impressions
  flow, the table is empty and this producer no-ops cleanly.
  :func:`load_relevance_table` returns ``{}`` for any consumer that
  asks; consumers fall back to neutral / cold-start behaviour.
- **Real-data ready.** The moment SuggestionImpression rows exist,
  the producer fits a real cascade model on the next scheduled run
  with no code changes required.
- **Additive to** :mod:`apps.pipeline.services.feedback_relevance`.
  That module computes Cascade relevance from *review-queue history*
  (PipelineRun + Suggestion) — always-on data. This module computes
  Cascade relevance from *viewport impressions* — direct click data
  once available. They live in distinct AppSetting namespaces so
  neither overwrites the other; Group A.4 will wire consumers to
  prefer the impression-based table when populated and fall back
  to the review-queue table otherwise.

Persisted shape (JSON dict):

- ``cascade_click_em.relevance.json`` — ``{destination_pk: relevance}``
- ``cascade_click_em.observations`` — total impression count seen at
  fit time
- ``cascade_click_em.sessions`` — number of cascade sessions built
- ``cascade_click_em.fitted_at`` — ISO timestamp of the fit
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass

from .cascade_click_model import (
    DEFAULT_PRIOR_ALPHA,
    DEFAULT_PRIOR_BETA,
    ClickSession,
    estimate as cascade_estimate,
    prior_mean,
)

logger = logging.getLogger(__name__)


KEY_RELEVANCE = "cascade_click_em.relevance.json"
KEY_OBSERVATIONS = "cascade_click_em.observations"
KEY_SESSIONS = "cascade_click_em.sessions"
KEY_FITTED_AT = "cascade_click_em.fitted_at"

#: Lookback for the Cascade fit. Mirrors the IPS producer and the
#: Platt fit so calibration windows stay consistent.
DEFAULT_LOOKBACK_DAYS: int = 90

#: Minimum impression count before Cascade EM is meaningful. With
#: too few sessions, every doc is shown once or twice and the
#: Laplace prior dominates the estimate.
MIN_IMPRESSIONS_FOR_FIT: int = 200

#: Minimum number of cascade sessions before the fit runs. Cascade
#: needs many ranked-list-with-click sessions to estimate per-doc
#: relevance robustly.
MIN_SESSIONS_FOR_FIT: int = 20


@dataclass(frozen=True)
class CascadeSnapshot:
    """The persisted Cascade EM result."""

    relevance: dict[int, float]
    observations: int
    sessions: int
    fitted_at: str | None


def load_relevance_table() -> dict[int, float]:
    """Return the persisted Cascade relevance table or ``{}``.

    Cold-start safe: missing AppSetting row → ``{}``. Malformed JSON
    → logged warning + ``{}``.
    """
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return {}
    row = AppSetting.objects.filter(key=KEY_RELEVANCE).first()
    if row is None or not row.value:
        return {}
    try:
        raw = json.loads(row.value)
    except (TypeError, ValueError):
        logger.warning("cascade_click_em_producer: malformed relevance JSON")
        return {}
    return {int(k): float(v) for k, v in raw.items()}


def load_snapshot() -> CascadeSnapshot | None:
    """Return the full persisted snapshot or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover
        return None
    rows = dict(
        AppSetting.objects.filter(
            key__in=[KEY_RELEVANCE, KEY_OBSERVATIONS, KEY_SESSIONS, KEY_FITTED_AT]
        ).values_list("key", "value")
    )
    if KEY_RELEVANCE not in rows:
        return None
    try:
        raw = json.loads(rows[KEY_RELEVANCE] or "{}")
        relevance = {int(k): float(v) for k, v in raw.items()}
        observations = int(rows.get(KEY_OBSERVATIONS, "0") or "0")
        sessions = int(rows.get(KEY_SESSIONS, "0") or "0")
    except (TypeError, ValueError):
        logger.warning("cascade_click_em_producer: malformed snapshot row")
        return None
    return CascadeSnapshot(
        relevance=relevance,
        observations=observations,
        sessions=sessions,
        fitted_at=rows.get(KEY_FITTED_AT),
    )


def relevance_for(destination_pk: int) -> float:
    """Return the Cascade-EM relevance for *destination_pk*.

    Cold-start fallback is the prior mean ``α / (α + β) = 0.5``,
    matching :func:`feedback_relevance.cascade_relevance_for` for
    consumer compatibility.
    """
    table = load_relevance_table()
    if not table:
        return prior_mean()
    return table.get(int(destination_pk), prior_mean())


# ── Producer ──────────────────────────────────────────────────────


def fit_and_persist_from_impressions(
    *,
    days_lookback: int = DEFAULT_LOOKBACK_DAYS,
    min_impressions: int = MIN_IMPRESSIONS_FOR_FIT,
    min_sessions: int = MIN_SESSIONS_FOR_FIT,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
) -> CascadeSnapshot | None:
    """Fit Cascade relevance from ``SuggestionImpression`` and persist.

    Session grouping
    ----------------
    Each ``PipelineRun`` becomes one cascade session:

    - ``ranked_docs`` = the run's distinct destination IDs ordered by
      the *first* impression position recorded for each suggestion.
    - ``clicked_rank`` = the 1-based position of the lowest-ranked
      impression with ``clicked=True``, or ``None`` if no click was
      logged. Cascade assumes one click per session.

    This grouping uses the pipeline_run as a session proxy. It's
    less precise than a frontend-stamped session_id (multiple
    operator visits to the same run get merged) but it's robust on
    cold-start and doesn't require a schema change. A future
    refinement can add a per-impression session_id and re-group.

    Cold-start safe
    ---------------
    - ``< min_impressions`` rows → return None, leave AppSetting
      untouched.
    - ``< min_sessions`` distinct pipeline_runs → return None.
    - Cascade ``estimate`` raises (e.g. invalid clicked_rank) → caught,
      return None.

    Idempotent: re-running on the same data produces the same
    relevance table.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import AppSetting
    from apps.suggestions.models import SuggestionImpression

    cutoff = timezone.now() - timedelta(days=days_lookback)
    rows = list(
        SuggestionImpression.objects.filter(impressed_at__gte=cutoff)
        .values_list(
            "suggestion__pipeline_run_id",
            "suggestion__destination_id",
            "position",
            "clicked",
            "impressed_at",
        )
        .order_by("suggestion__pipeline_run_id", "impressed_at")
    )
    if len(rows) < min_impressions:
        logger.info(
            "cascade_click_em_producer: %d impressions (< %d minimum), " "skipping fit",
            len(rows),
            min_impressions,
        )
        return None

    # Group impressions by pipeline_run. Within each group, build the
    # ranked-doc list ordered by the first position each destination
    # appeared at. Determine clicked_rank by scanning for the lowest
    # 1-based position with clicked=True.
    by_run: dict[int, list[tuple[int, int, bool]]] = defaultdict(list)
    for run_id, dest_id, position, clicked, _ in rows:
        if run_id is None or dest_id is None:
            # Defensive: skip orphan impressions whose suggestion's
            # FK chain has been GC'd.
            continue
        by_run[int(run_id)].append((int(dest_id), int(position), bool(clicked)))

    sessions: list[ClickSession] = []
    for run_id, run_rows in by_run.items():
        # Order destinations by their first impression position.
        first_position: dict[int, int] = {}
        for dest_id, position, _ in run_rows:
            if dest_id not in first_position or position < first_position[dest_id]:
                first_position[dest_id] = position
        ranked_docs = sorted(first_position, key=first_position.get)
        if not ranked_docs:
            continue
        # Map dest_id → 1-based rank in ranked_docs.
        rank_of: dict[int, int] = {
            dest: rank + 1 for rank, dest in enumerate(ranked_docs)
        }
        # Find the lowest-ranked clicked dest. Cascade's one-click
        # assumption: take the topmost click only.
        clicked_rank: int | None = None
        for dest_id, _, clicked in run_rows:
            if not clicked:
                continue
            r = rank_of.get(dest_id)
            if r is None:
                continue
            if clicked_rank is None or r < clicked_rank:
                clicked_rank = r
        sessions.append(
            ClickSession(ranked_docs=ranked_docs, clicked_rank=clicked_rank)
        )

    if len(sessions) < min_sessions:
        logger.info(
            "cascade_click_em_producer: only %d sessions (< %d minimum), "
            "skipping fit",
            len(sessions),
            min_sessions,
        )
        return None

    try:
        table = cascade_estimate(
            sessions, prior_alpha=prior_alpha, prior_beta=prior_beta
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning(
            "cascade_click_em_producer: cascade_estimate failed (%s), "
            "keeping previous table",
            exc,
        )
        return None

    relevance = {int(doc_id): float(rec.relevance) for doc_id, rec in table.items()}

    fitted_at = timezone.now().isoformat()
    AppSetting.objects.update_or_create(
        key=KEY_RELEVANCE,
        defaults={
            "value": json.dumps(
                {str(k): v for k, v in relevance.items()},
                separators=(",", ":"),
            ),
            "description": (
                "Pick #34 Cascade Click Model — per-destination "
                "relevance fit from SuggestionImpression rows. "
                "Craswell et al. 2008 §3."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_OBSERVATIONS,
        defaults={
            "value": str(len(rows)),
            "description": "Total SuggestionImpression rows seen at fit time.",
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_SESSIONS,
        defaults={
            "value": str(len(sessions)),
            "description": "Number of cascade sessions built from impressions.",
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_FITTED_AT,
        defaults={
            "value": fitted_at,
            "description": "ISO timestamp of the most recent cascade fit.",
        },
    )

    return CascadeSnapshot(
        relevance=relevance,
        observations=len(rows),
        sessions=len(sessions),
        fitted_at=fitted_at,
    )
