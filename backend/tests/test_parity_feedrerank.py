"""RPT-001 Finding 3 — feedrerank C++/Python parity test.

Verifies that ``feedrerank.calculate_rerank_factors_batch`` (C++) produces
numerically identical results to the pure-Python reference formula in
``feedback_rerank.py`` (lines 151–177).

Tolerance: 1e-6 absolute.  Five edge-case scenarios cover the surfaces where
FTZ/DAZ floating-point mode differences are most likely to manifest.

Reference: Joachims, Swaminathan & Schnabel 2017
    "Unbiased Learning-to-Rank with Biased Feedback"
    DOI 10.1145/3077136.3080756, eq. 4
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


# ── Pure-Python reference (mirrors feedback_rerank.py lines 151-177) ────────


def _python_rerank_factor(
    n_success: int,
    n_total: int,
    exposure_prob: float,
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

    # PARITY: matches feedback_rerank.py line 161 — exposure discount
    score_exploit = exposure_prob * score_exploit_raw + (1.0 - exposure_prob) * 0.5

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
    exposure_probs: list[float]
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
        exposure_probs=[0.8, 0.6, 0.3, 1.0, 0.5],
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
        exposure_probs=[0.0, 0.001, 0.5, 1e-10, 0.0],
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
        exposure_probs=[0.0, 0.0, 0.0],
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
        exposure_probs=[1.0],
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
        exposure_probs=[1.0, 0.999, 0.001, 1.0],
        n_global=100000,
        alpha=1.0,
        beta=1.0,
        weight=0.5,
        exploration_rate=0.2,
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
                exposure_prob=scenario.exposure_probs[i],
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
        np.array(scenario.exposure_probs, dtype=np.float64),
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
    exposure_probs = np.array([1.0, 1.0, 0.0, 0.5], dtype=np.float64)

    factors = feedrerank.calculate_rerank_factors_batch(
        successes,
        totals,
        exposure_probs,
        100000,
        1.0,
        1.0,
        1.0,
        1.0,
    )
    factors = np.asarray(factors)

    assert np.all(factors >= 0.5), f"Factor below 0.5: {factors}"
    assert np.all(factors <= 2.0), f"Factor above 2.0: {factors}"
