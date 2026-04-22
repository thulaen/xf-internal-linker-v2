"""Position-bias IPS estimator (Joachims, Swaminathan, Schnabel 2017).

Reference
---------
Joachims, T., Swaminathan, A. & Schnabel, T. (2017). "Unbiased
learning-to-rank with biased feedback." *Proceedings of the Tenth ACM
WSDM Conference*, pp. 781-789.

Goal
----
Click data is biased: users are more likely to click position 1 than
position 10 even when the items are equally relevant. If we train a
ranker on raw click-through rates, it learns "put clicked-on items
at the top" which is a tautology, not relevance.

Joachims et al. give a clean fix: inverse-propensity scoring (IPS).
Each display position ``d`` has an **examination propensity**
``p(d) ∈ (0, 1]`` — the probability a user examines position ``d``
given it was shown. To debias a click-through aggregate, divide each
observed click by that propensity::

    weighted_click(d) = click(d) / p(d)

Items at low-propensity positions (deep results, right-rail) thus
have their clicks scaled up; items at high-propensity positions
(top of page) have theirs scaled down. Train the ranker on the
weighted clicks — the gradient is unbiased under mild assumptions.

The paper's §4 power-law estimator is the default::

    p(d) = 1 / d^η

with ``η ≈ 1`` on typical SERPs. ``η`` can also be fit from
intervention data (swap experiments) via maximum likelihood.

Both modes are implemented here: a pure analytical propensity
function for when no intervention data is available, and a
:func:`fit_eta_from_interventions` routine that learns ``η`` from
swap-experiment logs (see Joachims §4.3).

**Clipping note.** Division by a tiny propensity makes the IPS
estimator high-variance. The paper recommends clipping the weight
at some maximum (Swaminathan-Joachims 2015 "Counterfactual Risk
Minimization"). We expose a ``max_weight`` cap so callers can dial
bias-variance trade-off explicitly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize_scalar


#: Default exponent for the power-law propensity. Joachims et al. §5
#: measured η ≈ 0.9-1.1 on the Yahoo and Arxiv SERPs they studied;
#: 1.0 is a robust starting point when no intervention data is
#: available.
DEFAULT_POWER_LAW_ETA: float = 1.0

#: Default clip on the IPS weight. ``10.0`` means a position with
#: propensity ``0.1`` never reweights beyond 10×. Swaminathan-Joachims
#: 2015 recommend setting this based on the variance / bias tolerance
#: of the downstream learner.
DEFAULT_MAX_WEIGHT: float = 10.0


@dataclass(frozen=True)
class InterventionLog:
    """One swap-experiment row.

    ``original_position`` — where the doc was *ranked* by the
    production ranker. ``shown_position`` — where the doc was
    actually *displayed* after the swap intervention.
    ``clicked`` — whether the user clicked on the shown item.
    """

    original_position: int
    shown_position: int
    clicked: bool


def power_law_propensity(
    position: int,
    *,
    eta: float = DEFAULT_POWER_LAW_ETA,
) -> float:
    """Return ``1 / position^η`` for a 1-based display *position*.

    Raises
    ------
    ValueError
        If ``position`` < 1 or ``eta`` <= 0.
    """
    if position < 1:
        raise ValueError("position must be >= 1 (1-based rank)")
    if eta <= 0:
        raise ValueError("eta must be > 0")
    return 1.0 / math.pow(position, eta)


def ips_weight(
    *,
    position: int,
    eta: float = DEFAULT_POWER_LAW_ETA,
    max_weight: float = DEFAULT_MAX_WEIGHT,
) -> float:
    """Return the clipped IPS weight for a 1-based *position*.

    ``weight = min( 1 / p(position), max_weight )``.
    """
    if max_weight <= 0:
        raise ValueError("max_weight must be > 0")
    raw = 1.0 / power_law_propensity(position, eta=eta)
    return min(raw, max_weight)


def reweight_clicks(
    position_click_counts: Mapping[int, int],
    *,
    eta: float = DEFAULT_POWER_LAW_ETA,
    max_weight: float = DEFAULT_MAX_WEIGHT,
) -> dict[int, float]:
    """Turn per-position raw click counts into IPS-weighted clicks.

    The return dict has the same keys as the input, with values in
    "equivalent un-biased clicks" — a float, not an int.
    """
    return {
        pos: count * ips_weight(position=pos, eta=eta, max_weight=max_weight)
        for pos, count in position_click_counts.items()
    }


def fit_eta_from_interventions(
    logs: Iterable[InterventionLog],
    *,
    eta_min: float = 0.1,
    eta_max: float = 3.0,
) -> float:
    """Fit the propensity exponent ``η`` from swap-experiment data.

    Following Joachims et al. §4.3: assume the click-through ratio
    between "document shown at position i" and "document shown at
    its original position j" factors as ``p(i) / p(j)``. Fit ``η``
    by maximising the Bernoulli log-likelihood over the observed
    clicks, with the power-law ``p(d) = 1 / d^η`` plugged in.

    Returns ``eta`` in ``[eta_min, eta_max]``.

    Raises
    ------
    ValueError
        If there are no logs or no clicks in the logs.
    """
    rows = list(logs)
    if not rows:
        raise ValueError("need at least one intervention log")
    original = np.array([r.original_position for r in rows], dtype=float)
    shown = np.array([r.shown_position for r in rows], dtype=float)
    clicked = np.array([r.clicked for r in rows], dtype=float)
    if np.sum(clicked) == 0:
        raise ValueError("need at least one clicked intervention log")

    def neg_log_likelihood(eta: float) -> float:
        if eta <= 0:
            return float("inf")
        # Probability of click under the power-law propensity, with
        # the ranker's latent relevance absorbed into a per-row
        # baseline: p(click) ≈ p(shown) / p(original). Clamp to (ε, 1).
        ratio = np.power(original, eta) / np.power(shown, eta)
        # Sigmoid-like squash keeps the log finite and mirrors the
        # paper's treatment for ratios > 1 (the swap improved
        # examination, boosting click probability).
        p = np.clip(ratio / (1.0 + ratio), 1e-9, 1.0 - 1e-9)
        return float(-np.sum(clicked * np.log(p) + (1.0 - clicked) * np.log(1.0 - p)))

    res = minimize_scalar(
        neg_log_likelihood,
        bounds=(eta_min, eta_max),
        method="bounded",
    )
    return float(res.x)


def average_reweighted_click_rate(
    *,
    click_events: Sequence[tuple[int, bool]],
    eta: float = DEFAULT_POWER_LAW_ETA,
    max_weight: float = DEFAULT_MAX_WEIGHT,
) -> float:
    """Return the IPS-weighted click-through rate for a click stream.

    Each element of ``click_events`` is ``(position, was_clicked)``.
    Output is a single scalar — the sum of IPS-weighted clicks
    divided by the number of impressions. Useful for aggregate
    dashboards (unbiased CTR).
    """
    if not click_events:
        return 0.0
    weighted_clicks = 0.0
    for position, was_clicked in click_events:
        if was_clicked:
            weighted_clicks += ips_weight(
                position=position, eta=eta, max_weight=max_weight
            )
    return weighted_clicks / len(click_events)
