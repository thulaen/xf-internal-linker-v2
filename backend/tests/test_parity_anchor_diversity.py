"""FR-045 anchor diversity C++/Python parity test (closes ISS-020).

Verifies that ``evaluate_anchor_diversity_batch`` produces numerically
identical results regardless of whether the compiled C++ extension is
used or the pure-Python fallback runs. Five scenarios cover every state
branch in the scorer:

1. Insufficient history (``neutral_no_history``)
2. Below-threshold share (``neutral_below_threshold``)
3. Share penalty (``penalized_exact_share``)
4. Count penalty (``penalized_exact_count``)
5. Hard-cap block (``blocked_exact_count``)

Tolerance: 1e-6 absolute, 0 relative — matches ``test_parity_feedrerank.py``
and the CPP-RULES §25 PARITY floor.

Source: Google Search Central link best-practices + US20110238644A1.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pytest

from apps.pipeline.services.anchor_diversity import (
    HAS_CPP_EXT,
    AnchorDiversitySettings,
    AnchorHistory,
    evaluate_anchor_diversity_batch,
)
from apps.pipeline.services import anchor_diversity as _ad


class Scenario(NamedTuple):
    """One parity-test input covering a specific state branch."""

    name: str
    settings: AnchorDiversitySettings
    destination_key: tuple[int, str]
    history: AnchorHistory
    candidate_anchor: str


SCENARIOS = [
    Scenario(
        name="neutral_no_history",
        settings=AnchorDiversitySettings(),
        destination_key=(1, "thread"),
        history=AnchorHistory(active_anchor_count=1, exact_match_counts={}),
        candidate_anchor="weekend camping trip",
    ),
    Scenario(
        name="neutral_below_threshold",
        settings=AnchorDiversitySettings(),
        destination_key=(2, "thread"),
        history=AnchorHistory(
            active_anchor_count=10,
            exact_match_counts={"weekend camping trip": 1, "sleep gear": 2},
        ),
        candidate_anchor="weekend camping trip",
    ),
    Scenario(
        name="penalized_exact_share",
        settings=AnchorDiversitySettings(),
        destination_key=(3, "thread"),
        history=AnchorHistory(
            active_anchor_count=5,
            exact_match_counts={"weekend camping trip": 2},
        ),
        candidate_anchor="weekend camping trip",
    ),
    Scenario(
        name="penalized_exact_count",
        settings=AnchorDiversitySettings(
            max_exact_match_share=0.99,  # disarm the share trigger to isolate count
        ),
        destination_key=(4, "thread"),
        history=AnchorHistory(
            active_anchor_count=20,
            exact_match_counts={"weekend camping trip": 5},
        ),
        candidate_anchor="weekend camping trip",
    ),
    Scenario(
        name="blocked_exact_count",
        settings=AnchorDiversitySettings(hard_cap_enabled=True),
        destination_key=(5, "thread"),
        history=AnchorHistory(
            active_anchor_count=8,
            exact_match_counts={"weekend camping trip": 4},
        ),
        candidate_anchor="weekend camping trip",
    ),
]


def _run_scenario(scenario: Scenario, *, force_python: bool):
    """Run a scenario through evaluate_anchor_diversity_batch with either
    path forced. Monkey-patches the module-level HAS_CPP_EXT flag so the
    C++ and Python paths can be exercised side-by-side inside one test.
    """
    saved = _ad.HAS_CPP_EXT
    try:
        _ad.HAS_CPP_EXT = not force_python and saved
        results = evaluate_anchor_diversity_batch(
            destination_keys=[scenario.destination_key],
            candidate_anchor_texts=[scenario.candidate_anchor],
            history_by_destination={scenario.destination_key: scenario.history},
            settings=scenario.settings,
        )
    finally:
        _ad.HAS_CPP_EXT = saved
    return results[0]


_NUMERIC_DIAGNOSTIC_KEYS = (
    "projected_exact_match_count",
    "projected_exact_share",
    "share_overflow",
    "count_overflow_norm",
    "spam_risk",
    "score_anchor_diversity",
)


@pytest.mark.skipif(
    not HAS_CPP_EXT, reason="C++ anchor_diversity extension not compiled"
)
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_anchor_diversity_cpp_matches_python(scenario: Scenario) -> None:
    """C++ and Python paths must agree to 1e-6 on every numeric field."""
    py_result = _run_scenario(scenario, force_python=True)
    cpp_result = _run_scenario(scenario, force_python=False)

    # Top-level score + component + block decision.
    np.testing.assert_allclose(
        cpp_result.score_anchor_diversity,
        py_result.score_anchor_diversity,
        atol=1e-6,
        rtol=0,
        err_msg=f"[{scenario.name}] score_anchor_diversity divergence",
    )
    np.testing.assert_allclose(
        cpp_result.score_component,
        py_result.score_component,
        atol=1e-6,
        rtol=0,
        err_msg=f"[{scenario.name}] score_component divergence",
    )
    assert (
        cpp_result.blocked == py_result.blocked
    ), f"[{scenario.name}] blocked flag divergence"
    assert (
        cpp_result.repeated_anchor == py_result.repeated_anchor
    ), f"[{scenario.name}] repeated_anchor divergence"

    # Every numeric field in the diagnostics dict.
    for key in _NUMERIC_DIAGNOSTIC_KEYS:
        np.testing.assert_allclose(
            cpp_result.diagnostics[key],
            py_result.diagnostics[key],
            atol=1e-6,
            rtol=0,
            err_msg=f"[{scenario.name}] diagnostics[{key!r}] divergence",
        )

    # State + algorithm_version strings must match byte-for-byte.
    assert (
        cpp_result.diagnostics["anchor_diversity_state"]
        == py_result.diagnostics["anchor_diversity_state"]
    ), f"[{scenario.name}] anchor_diversity_state divergence"
    assert (
        cpp_result.diagnostics["algorithm_version"]
        == py_result.diagnostics["algorithm_version"]
    )
    # The runtime_path key distinguishes which path ran.
    assert cpp_result.diagnostics.get("runtime_path") == "cpp"
    assert py_result.diagnostics.get("runtime_path") == "python"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_python_batch_matches_per_candidate(scenario: Scenario) -> None:
    """The Python-fallback batch path must match the per-candidate
    ``evaluate_anchor_diversity`` reference exactly (excluding the
    batch-only ``runtime_path`` key). Runs regardless of whether the
    C++ extension is compiled.
    """
    from apps.pipeline.services.anchor_diversity import evaluate_anchor_diversity

    per_candidate = evaluate_anchor_diversity(
        destination_key=scenario.destination_key,
        candidate_anchor_text=scenario.candidate_anchor,
        history_by_destination={scenario.destination_key: scenario.history},
        settings=scenario.settings,
    )
    batch = _run_scenario(scenario, force_python=True)

    # Numeric parity at 1e-6.
    np.testing.assert_allclose(
        batch.score_anchor_diversity,
        per_candidate.score_anchor_diversity,
        atol=1e-6,
        rtol=0,
    )
    assert batch.blocked == per_candidate.blocked
    assert batch.repeated_anchor == per_candidate.repeated_anchor
    for key in _NUMERIC_DIAGNOSTIC_KEYS:
        if key in per_candidate.diagnostics:
            np.testing.assert_allclose(
                batch.diagnostics[key],
                per_candidate.diagnostics[key],
                atol=1e-6,
                rtol=0,
                err_msg=f"[{scenario.name}] diagnostics[{key!r}] differs from per-candidate",
            )
    assert (
        batch.diagnostics["anchor_diversity_state"]
        == per_candidate.diagnostics["anchor_diversity_state"]
    )
