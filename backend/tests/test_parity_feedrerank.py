"""RPT-001 Finding 3 — feedrerank C++/Python parity test.

Verifies that ``feedrerank.calculate_rerank_factors_batch`` (C++) produces
numerically identical results to the pure-Python reference formula in
``feedback_rerank.py``.

Tolerance: 1e-6 absolute.  Six edge-case scenarios cover the surfaces where
FTZ/DAZ floating-point mode differences are most likely to manifest,
including the zero-priors denominator guard (RPT-001 Finding 3) and the
linear observation_confidence blend toward neutral 0.5 (RPT-001 Finding 2,
resolved 2026-04-20 — this is NOT an inverse-propensity estimator).
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pytest

try:
    from extensions import feedrerank

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False


# ── Pure-Python reference (mirrors feedback_rerank.py) ──────────────────────


def _python_rerank_factor(
    n_success: int,
    n_total: int,
    observation_confidence: float,
    n_global: int,
    alpha: float,
    beta: float,
    weight: float,
    exploration_rate: float,
) -> float:
    """Pure-Python single-pair rerank factor — the reference truth."""
    # PARITY: matches feedback_rerank.py line 156 — exploit numerator
    exploit_denom = n_total + alpha + beta
    score_exploit_raw = (n_success + alpha) / max(exploit_denom, 1e-9)

    # PARITY: matches feedback_rerank.py line 161 — linear observation_confidence
    # blend toward neutral 0.5. This is NOT an inverse-propensity estimator
    # (see RPT-001 Finding 2 resolved 2026-04-20).
    score_exploit = (
        observation_confidence * score_exploit_raw
        + (1.0 - observation_confidence) * 0.5
    )

    # PARITY: matches feedback_rerank.py line 166 — UCB1 explore
    score_explore = exploration_rate * math.sqrt(
        math.log(n_global + 1.0) / (n_total + 1.0)
    )

    # PARITY: matches feedback_rerank.py line 173 — combined modifier
    raw_modifier = (score_exploit + score_explore) - 0.5

    # PARITY: matches feedback_rerank.py line 174 — weighted factor
    factor = 1.0 + (weight * raw_modifier)

    # PARITY: matches feedback_rerank.py line 177 — clamp to [0.5, 2.0]
    return max(0.5, min(2.0, factor))


# ── Test scenarios ──────────────────────────────────────────────────────────


class Scenario(NamedTuple):
    """A parity test scenario with named parameters."""

    name: str
    successes: list[int]
    totals: list[int]
    observation_confidences: list[float]
    n_global: int
    alpha: float
    beta: float
    weight: float
    exploration_rate: float


SCENARIOS: list[Scenario] = [
    Scenario(
        name="normal_distribution",
        successes=[10, 25, 0, 50, 5],
        totals=[20, 50, 10, 100, 30],
        observation_confidences=[0.8, 0.6, 0.3, 1.0, 0.5],
        n_global=10000,
        alpha=1.0,
        beta=1.0,
        weight=0.3,
        exploration_rate=0.1,
    ),
    Scenario(
        name="near_zero_totals",
        successes=[0, 0, 1, 0, 0],
        totals=[0, 0, 1, 0, 0],
        observation_confidences=[0.0, 0.001, 0.5, 1e-10, 0.0],
        n_global=1,
        alpha=1.0,
        beta=1.0,
        weight=0.3,
        exploration_rate=0.1,
    ),
    Scenario(
        name="cold_start_no_history",
        successes=[0, 0, 0],
        totals=[0, 0, 0],
        observation_confidences=[0.0, 0.0, 0.0],
        n_global=0,
        alpha=1.0,
        beta=1.0,
        weight=0.3,
        exploration_rate=0.1,
    ),
    Scenario(
        name="single_observation",
        successes=[1],
        totals=[1],
        observation_confidences=[1.0],
        n_global=1,
        alpha=1.0,
        beta=1.0,
        weight=0.3,
        exploration_rate=0.1,
    ),
    Scenario(
        name="max_values_stress",
        successes=[999, 500, 0, 1000],
        totals=[1000, 1000, 1000, 1000],
        observation_confidences=[1.0, 0.999, 0.001, 1.0],
        n_global=100000,
        alpha=1.0,
        beta=1.0,
        weight=0.5,
        exploration_rate=0.2,
    ),
    # RPT-001 Finding 3 — the exploit denominator guard. Python uses
    # max(denom, 1e-9) to avoid division-by-zero; pre-fix C++ did the
    # division without the guard and emitted Infinity/NaN. With
    # alpha=beta=0 and total=0 the denominator is zero, so the guard
    # is exercised. Kept as its own scenario so a future refactor
    # cannot drop the guard without this test failing.
    Scenario(
        name="zero_priors_denominator_guard",
        successes=[5, 0, 2, 3],
        totals=[0, 0, 0, 0],
        observation_confidences=[1.0, 1.0, 0.5, 0.8],
        n_global=1000,
        alpha=0.0,
        beta=0.0,
        weight=0.3,
        exploration_rate=0.1,
    ),
]


@pytest.mark.skipif(not HAS_CPP_EXT, reason="C++ feedrerank extension not available")
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_feedrerank_parity(scenario: Scenario) -> None:
    """C++ must match Python reference within 1e-6 absolute tolerance."""
    n = len(scenario.successes)

    # --- Python reference ---
    py_factors = np.array(
        [
            _python_rerank_factor(
                n_success=scenario.successes[i],
                n_total=scenario.totals[i],
                observation_confidence=scenario.observation_confidences[i],
                n_global=scenario.n_global,
                alpha=scenario.alpha,
                beta=scenario.beta,
                weight=scenario.weight,
                exploration_rate=scenario.exploration_rate,
            )
            for i in range(n)
        ]
    )

    # --- C++ batch ---
    cpp_factors = feedrerank.calculate_rerank_factors_batch(
        np.array(scenario.successes, dtype=np.int32),
        np.array(scenario.totals, dtype=np.int32),
        np.array(scenario.observation_confidences, dtype=np.float64),
        scenario.n_global,
        scenario.alpha,
        scenario.beta,
        scenario.weight,
        scenario.exploration_rate,
    )
    cpp_factors = np.asarray(cpp_factors)

    # --- Parity assertion at 1e-6 ---
    np.testing.assert_allclose(
        cpp_factors,
        py_factors,
        atol=1e-6,
        rtol=0,
        err_msg=(
            f"Scenario '{scenario.name}': C++ and Python diverge beyond 1e-6.\n"
            f"  Python: {py_factors}\n"
            f"  C++:    {cpp_factors}\n"
            f"  Diff:   {np.abs(cpp_factors - py_factors)}"
        ),
    )


@pytest.mark.skipif(not HAS_CPP_EXT, reason="C++ feedrerank extension not available")
def test_feedrerank_factor_bounds() -> None:
    """All factors must be clamped to [0.5, 2.0] regardless of input."""
    # Extreme inputs designed to push factor outside clamp range
    successes = np.array([0, 1000, 0, 500], dtype=np.int32)
    totals = np.array([1000, 1000, 0, 500], dtype=np.int32)
    observation_confidences = np.array([1.0, 1.0, 0.0, 0.5], dtype=np.float64)

    factors = feedrerank.calculate_rerank_factors_batch(
        successes,
        totals,
        observation_confidences,
        100000,
        1.0,
        1.0,
        1.0,
        1.0,
    )
    factors = np.asarray(factors)

    assert np.all(factors >= 0.5), f"Factor below 0.5: {factors}"
    assert np.all(factors <= 2.0), f"Factor above 2.0: {factors}"
