"""Exponential moving-average feedback aggregator (Brown 1959).

Reference
---------
Brown, R. G. (1959). "Statistical forecasting for inventory control."
*Operations Research* 7(6): 691-705.

Goal
----
Turn a noisy stream of per-suggestion feedback events (accepts /
rejects / edits / click-throughs) into a single smoothed score per
item so the reranker can prioritise suggestions that have been
consistently well-received over ones that landed a single lucky
accept last week.

Brown's EMA recurrence::

    s_t = α * x_t + (1 - α) * s_{t-1}

with ``α ∈ (0, 1]`` acting as a smoothing constant. Smaller ``α``
means longer memory — a single bad event barely moves the score.
Larger ``α`` means the estimate reacts quickly to recent signal at
the cost of being noisier.

The helper is pure arithmetic — no I/O, no Django — so the scheduler
job feeds pre-aggregated per-item time series in and gets per-item
EMA + an aggregated drift metric back.

Half-life helper
----------------
Operators think in "the last week's feedback should matter more
than last month's"; the smoothing constant is an awkward lever for
that. :func:`alpha_from_half_life` converts a half-life in event
counts (how many events until an old signal loses half its weight)
into the equivalent ``α``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


#: Default α. Halves an event's influence every ~7 steps, which is
#: a sensible balance for the linker's daily feedback cadence — one
#: week of recent clicks dominates the older tail.
DEFAULT_ALPHA: float = 0.1


@dataclass(frozen=True)
class EMASummary:
    """Result of running EMA over a single series."""

    final_value: float
    observation_count: int
    smoothing_alpha: float


def alpha_from_half_life(half_life_steps: float) -> float:
    """Return the α whose decay halves an event's weight after N steps.

    Formally ``α = 1 - 0.5^(1/N)``. Callers pass the half-life in the
    same units as their event stream (daily aggregates → half-life in
    days, click events → half-life in clicks, …).

    Raises
    ------
    ValueError
        If ``half_life_steps`` is not strictly positive.
    """
    if half_life_steps <= 0:
        raise ValueError("half_life_steps must be > 0")
    return 1.0 - math.pow(0.5, 1.0 / half_life_steps)


def ema(
    series: Sequence[float],
    *,
    alpha: float = DEFAULT_ALPHA,
    seed: float | None = None,
) -> EMASummary:
    """Return the EMA summary for *series*.

    Parameters
    ----------
    series
        Observations in chronological order.
    alpha
        Smoothing constant. Must lie in (0, 1].
    seed
        Initial value of ``s_0``. When ``None``, the first observation
        is used verbatim (standard Brown 1959 convention); otherwise
        the caller can carry state across calls by passing the
        previous summary's ``final_value``.

    Empty ``series`` + ``seed=None`` → :class:`EMASummary` with
    ``final_value=0.0`` and ``observation_count=0``. Callers can
    detect the degenerate case via ``observation_count``.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")

    observations = list(series)
    if seed is None:
        if not observations:
            return EMASummary(
                final_value=0.0,
                observation_count=0,
                smoothing_alpha=alpha,
            )
        current = float(observations[0])
        start = 1
    else:
        current = float(seed)
        start = 0

    for obs in observations[start:]:
        current = alpha * float(obs) + (1.0 - alpha) * current

    return EMASummary(
        final_value=current,
        observation_count=len(observations),
        smoothing_alpha=alpha,
    )


def ema_per_key(
    series_by_key: Mapping[str, Iterable[float]],
    *,
    alpha: float = DEFAULT_ALPHA,
    seeds: Mapping[str, float] | None = None,
) -> dict[str, EMASummary]:
    """Apply :func:`ema` independently to each keyed series.

    Convenience wrapper so the scheduler job can aggregate many
    per-suggestion streams in a single call.
    """
    seeds = seeds or {}
    return {
        key: ema(list(series), alpha=alpha, seed=seeds.get(key))
        for key, series in series_by_key.items()
    }
