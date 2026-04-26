"""Producer + read API for pick #33 IPS Position Bias.

The math helper at :mod:`apps.pipeline.services.position_bias_ips`
takes a propensity-exponent ``η`` and returns clipped inverse-
propensity weights. This module is the producer side: read the
``SuggestionImpression`` log, fit ``η`` from observed click-rate by
position, persist to AppSetting.

Cold-start safe: zero impressions (frontend hook not landed yet)
→ producer no-ops cleanly, and :func:`load_eta` returns the default
``η = 1.0`` for any consumer that asks.

Persisted shape (mirrors Phase 4 #32 Platt + pick #50 conformal):

- ``position_bias_ips.eta`` — fitted exponent (default 1.0)
- ``position_bias_ips.max_weight`` — clip on the IPS weight
- ``position_bias_ips.observations`` — total impression count seen at fit time
- ``position_bias_ips.fitted_at`` — ISO timestamp of the most recent fit

The W1 ``position_bias_ips_refit`` scheduled job calls
:func:`fit_and_persist_from_impressions` daily. Consumers (Group A.4
will wire feedback_relevance, future ranker reweighting) read
:func:`load_eta` then call ``position_bias_ips.ips_weight``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from .position_bias_ips import (
    DEFAULT_MAX_WEIGHT,
    DEFAULT_POWER_LAW_ETA,
    InterventionLog,
    fit_eta_from_interventions,
    ips_weight,
)

logger = logging.getLogger(__name__)


KEY_ETA = "position_bias_ips.eta"
KEY_MAX_WEIGHT = "position_bias_ips.max_weight"
KEY_OBSERVATIONS = "position_bias_ips.observations"
KEY_FITTED_AT = "position_bias_ips.fitted_at"

#: Lookback for the calibration set. Mirrors the Platt fit-job
#: lookback so calibration jobs share a consistent rolling window.
DEFAULT_LOOKBACK_DAYS: int = 90

#: Minimum impression count before a fit is meaningful. Below this
#: ``fit_eta_from_interventions`` produces a high-variance estimate
#: that's worse than the default ``η=1.0``.
MIN_IMPRESSIONS_FOR_FIT: int = 200


@dataclass(frozen=True)
class IpsSnapshot:
    """The persisted IPS calibration."""

    eta: float
    max_weight: float
    observations: int
    fitted_at: str | None


def load_eta(*, default: float = DEFAULT_POWER_LAW_ETA) -> float:
    """Return the persisted IPS exponent or *default* on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return default
    row = AppSetting.objects.filter(key=KEY_ETA).first()
    if row is None:
        return default
    try:
        return float(row.value)
    except (TypeError, ValueError):
        logger.warning("position_bias_ips_producer: malformed eta row, using default")
        return default


def load_snapshot() -> IpsSnapshot | None:
    """Return the full persisted IPS snapshot, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover
        return None
    rows = dict(
        AppSetting.objects.filter(
            key__in=[KEY_ETA, KEY_MAX_WEIGHT, KEY_OBSERVATIONS, KEY_FITTED_AT]
        ).values_list("key", "value")
    )
    if KEY_ETA not in rows:
        return None
    try:
        return IpsSnapshot(
            eta=float(rows[KEY_ETA]),
            max_weight=float(rows.get(KEY_MAX_WEIGHT, str(DEFAULT_MAX_WEIGHT))),
            observations=int(rows.get(KEY_OBSERVATIONS, "0") or "0"),
            fitted_at=rows.get(KEY_FITTED_AT),
        )
    except (TypeError, ValueError):
        logger.warning("position_bias_ips_producer: malformed AppSetting row, ignoring")
        return None


def ips_weight_for_position(
    position: int, *, snapshot: IpsSnapshot | None = None
) -> float:
    """Return the clipped IPS weight for a 1-based *position*.

    Uses the persisted ``η`` when a snapshot exists, otherwise falls
    back to the helper's default ``η=1.0``. Snapshot is optional so
    consumers that already loaded it (e.g. once per pipeline pass)
    don't pay a second AppSetting query per call.
    """
    snap = snapshot if snapshot is not None else load_snapshot()
    if snap is None:
        return ips_weight(position=position)
    return ips_weight(position=position, eta=snap.eta, max_weight=snap.max_weight)


# ── Producer ──────────────────────────────────────────────────────


def fit_and_persist_from_impressions(
    *,
    days_lookback: int = DEFAULT_LOOKBACK_DAYS,
    min_impressions: int = MIN_IMPRESSIONS_FOR_FIT,
    max_weight: float = DEFAULT_MAX_WEIGHT,
) -> IpsSnapshot | None:
    """Fit ``η`` from ``SuggestionImpression`` rows and persist it.

    The Joachims et al. 2017 paper fits ``η`` from swap-experiment
    intervention logs (``original_position``, ``shown_position``,
    ``clicked``). We don't run swap experiments — the production
    review queue ranks suggestions in score order and shows them in
    that order. So ``original_position == shown_position == position``
    on every row, which makes the swap-experiment likelihood
    degenerate.

    What we *can* fit is the per-position click distribution. The
    helper's :func:`fit_eta_from_interventions` uses the same
    Bernoulli-likelihood machinery; feeding it
    ``InterventionLog(original_position=p, shown_position=p, clicked=c)``
    for each impression maximises the likelihood of the observed
    click-by-position curve under the power-law assumption.

    Cold-start safe: < ``min_impressions`` rows → returns None,
    leaves AppSetting untouched. Consumers fall back to ``η=1.0``.

    Idempotent: re-running on the same data produces the same η
    (within scipy's tolerance).
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import AppSetting
    from apps.suggestions.models import SuggestionImpression

    cutoff = timezone.now() - timedelta(days=days_lookback)
    rows = list(
        SuggestionImpression.objects.filter(impressed_at__gte=cutoff).values_list(
            "position", "clicked"
        )
    )
    if len(rows) < min_impressions:
        logger.info(
            "position_bias_ips_producer: %d impressions (< %d minimum), "
            "skipping fit",
            len(rows),
            min_impressions,
        )
        return None

    # Build (intervention, click) tuples. position is 0-based in the
    # SuggestionImpression model but the helper's power_law_propensity
    # is defined on 1-based ranks (rank 1 = top, propensity 1.0). Add 1
    # at this boundary so downstream math sees the rank convention it
    # expects.
    logs = [
        InterventionLog(
            original_position=int(position) + 1,
            shown_position=int(position) + 1,
            clicked=bool(clicked),
        )
        for position, clicked in rows
    ]

    # Spot-check: the fitter rejects degenerate position distributions.
    # If every impression is at position 1 (queue length 1), there's
    # nothing to fit — the helper raises ValueError. Catch it and
    # fall through to "use the default eta" rather than crash the job.
    by_position: dict[int, list[bool]] = defaultdict(list)
    for log in logs:
        by_position[log.shown_position].append(log.clicked)
    if len(by_position) < 2:
        logger.info(
            "position_bias_ips_producer: only %d distinct positions, " "skipping fit",
            len(by_position),
        )
        return None

    try:
        eta = fit_eta_from_interventions(logs)
    except (ValueError, RuntimeError) as exc:
        logger.warning(
            "position_bias_ips_producer: fit_eta failed (%s), keeping default",
            exc,
        )
        return None

    fitted_at = timezone.now().isoformat()
    for key, value in (
        (KEY_ETA, str(eta)),
        (KEY_MAX_WEIGHT, str(max_weight)),
        (KEY_OBSERVATIONS, str(len(logs))),
        (KEY_FITTED_AT, fitted_at),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": (
                    "Pick #33 IPS Position Bias — fitted daily from "
                    "SuggestionImpression rows. Joachims et al. 2017 §4."
                ),
            },
        )

    return IpsSnapshot(
        eta=float(eta),
        max_weight=float(max_weight),
        observations=len(logs),
        fitted_at=fitted_at,
    )
