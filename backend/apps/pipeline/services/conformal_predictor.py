"""Producer + read API for pick #50 split-conformal calibration.

Pick #50 attaches a distribution-free confidence band to each
suggestion's ``score_final`` so review-queue UIs can show "this
suggestion has a 90 % chance of falling within ±X of its score"
without making distributional assumptions about the underlying
ranker.

The math lives in :mod:`apps.pipeline.services.conformal_prediction`
(``fit`` / ``ConformalCalibration``). This module is the producer +
read API:

- :func:`fit_and_persist_from_history` — pull the recent reviewed-
  Suggestion accept/reject history (``score_final`` paired with a
  binary 1.0 / 0.0 label), fit a split-conformal interval, persist
  ``(alpha, half_width, calibration_set_size, fitted_at)`` to four
  AppSetting rows. Mirrors the W3a Platt fit/persist pattern so
  operators see one consistent shape across calibration jobs.
- :func:`load_snapshot` — read the four AppSettings; cold-start
  returns ``None``.
- :func:`predict_interval(score, snapshot)` — wrap a raw score with
  the persisted half-width.

The per-Suggestion consumer (``_build_suggestion_records``) loads
the snapshot once and applies it to every row in the batch — same
O(1) loader pattern Platt uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from .conformal_prediction import (
    ConformalCalibration,
    ConformalInterval,
    DEFAULT_ALPHA,
    fit,
)

logger = logging.getLogger(__name__)


#: AppSetting keys — the four-row Platt-style snapshot. Co-located
#: under ``conformal_prediction.*`` so the Settings tab can find
#: them as a group.
KEY_ALPHA = "conformal_prediction.alpha"
KEY_HALF_WIDTH = "conformal_prediction.half_width"
KEY_CALIBRATION_SET_SIZE = "conformal_prediction.calibration_set_size"
KEY_FITTED_AT = "conformal_prediction.fitted_at"

#: Minimum reviewed-pair count before a fit is meaningful. Below this
#: the empirical quantile is too noisy to act on.
MIN_CALIBRATION_PAIRS: int = 30

#: Default lookback for the calibration set.
DEFAULT_LOOKBACK_DAYS: int = 90

#: Suggestion statuses we accept as positive labels (``y=1``).
_POSITIVE_STATUSES: frozenset[str] = frozenset({"approved", "applied", "verified"})

#: Suggestion statuses we accept as negative labels (``y=0``).
_NEGATIVE_STATUSES: frozenset[str] = frozenset(
    {"rejected", "declined", "dismissed", "superseded"}
)


@dataclass(frozen=True)
class ConformalSnapshot:
    """Persisted calibration loaded from AppSetting."""

    alpha: float
    half_width: float
    calibration_set_size: int
    fitted_at: str | None

    def to_calibration(self) -> ConformalCalibration:
        return ConformalCalibration(
            alpha=self.alpha,
            half_width=self.half_width,
            calibration_set_size=self.calibration_set_size,
        )


# ── Read API ──────────────────────────────────────────────────────


def load_snapshot() -> ConformalSnapshot | None:
    """Return the persisted conformal calibration, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None

    rows = dict(
        AppSetting.objects.filter(
            key__in=[KEY_ALPHA, KEY_HALF_WIDTH, KEY_CALIBRATION_SET_SIZE, KEY_FITTED_AT]
        ).values_list("key", "value")
    )
    if KEY_ALPHA not in rows or KEY_HALF_WIDTH not in rows:
        return None
    try:
        alpha = float(rows[KEY_ALPHA])
        half_width = float(rows[KEY_HALF_WIDTH])
        n = int(rows.get(KEY_CALIBRATION_SET_SIZE, "0") or "0")
    except (TypeError, ValueError):
        logger.warning("conformal_predictor: malformed AppSetting row, ignoring")
        return None
    return ConformalSnapshot(
        alpha=alpha,
        half_width=half_width,
        calibration_set_size=n,
        fitted_at=rows.get(KEY_FITTED_AT),
    )


def predict_interval(
    score: float, *, snapshot: ConformalSnapshot | None = None
) -> ConformalInterval | None:
    """Return the conformal interval for *score*, or ``None`` on cold start.

    Cold-start returns None (rather than a fake [score, score] degenerate
    interval) so callers can render "no calibration yet" honestly.
    """
    snap = snapshot if snapshot is not None else load_snapshot()
    if snap is None:
        return None
    return snap.to_calibration().predict_interval(float(score))


# ── Producer ──────────────────────────────────────────────────────


def _collect_calibration_pairs(
    days_lookback: int = DEFAULT_LOOKBACK_DAYS,
) -> Iterable[tuple[float, float]]:
    """Yield ``(score, label)`` pairs from reviewed Suggestions.

    ``score`` is the persisted ``score_final``. ``label`` is 1.0 for
    approved/applied/verified rows and 0.0 for rejected/declined/etc.
    Pending-but-unreviewed rows are skipped — they have no operator
    label yet.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.suggestions.models import Suggestion

    cutoff = timezone.now() - timedelta(days=days_lookback)
    reviewed_q = Q(status__in=list(_POSITIVE_STATUSES | _NEGATIVE_STATUSES))
    rows = Suggestion.objects.filter(reviewed_q, updated_at__gte=cutoff).values_list(
        "score_final", "status"
    )
    for score, status in rows:
        if score is None:
            continue
        label = 1.0 if status in _POSITIVE_STATUSES else 0.0
        yield (float(score), label)


def fit_and_persist_from_history(
    *,
    days_lookback: int = DEFAULT_LOOKBACK_DAYS,
    alpha: float = DEFAULT_ALPHA,
    min_pairs: int = MIN_CALIBRATION_PAIRS,
) -> ConformalSnapshot | None:
    """Fit a split-conformal calibration from review history and persist it.

    Cold-start safe: returns ``None`` when fewer than ``min_pairs``
    reviewed Suggestions exist. The Suggestion-write consumer treats
    ``None`` snapshots as "no calibration yet" — review UI shows
    blanks instead of fake intervals.

    Idempotent: a re-run that finds the same calibration set produces
    the same snapshot. Subsequent runs that find a larger set
    typically tighten the half-width.
    """
    from django.utils import timezone

    from apps.core.models import AppSetting

    pairs = list(_collect_calibration_pairs(days_lookback=days_lookback))
    if len(pairs) < min_pairs:
        logger.info(
            "conformal_predictor: only %d reviewed pairs (< %d minimum), "
            "skipping fit",
            len(pairs),
            min_pairs,
        )
        return None

    scores = [s for s, _ in pairs]
    labels = [y for _, y in pairs]
    calibration = fit(
        calibration_scores=scores, calibration_labels=labels, alpha=alpha
    )

    fitted_at = timezone.now().isoformat()
    for key, value in (
        (KEY_ALPHA, str(calibration.alpha)),
        (KEY_HALF_WIDTH, str(calibration.half_width)),
        (KEY_CALIBRATION_SET_SIZE, str(calibration.calibration_set_size)),
        (KEY_FITTED_AT, fitted_at),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": (
                    "Pick #50 split-conformal calibration — fitted weekly "
                    "from reviewed-Suggestion (score, label) pairs."
                ),
            },
        )
    return ConformalSnapshot(
        alpha=calibration.alpha,
        half_width=calibration.half_width,
        calibration_set_size=calibration.calibration_set_size,
        fitted_at=fitted_at,
    )
