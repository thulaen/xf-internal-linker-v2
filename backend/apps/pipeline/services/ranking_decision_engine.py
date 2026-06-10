"""Python boundary for the Rust RankingDecisionEngine.

The Rust PyO3 module ``extensions.ranking_decision_engine`` owns ranking
decisions. This file intentionally contains no Python scoring fallback; it only
loads the Rust module and delegates calls.
"""

from __future__ import annotations

import importlib
from typing import Any

_KERNEL_MODULE = "extensions.ranking_decision_engine"
_FUNCTIONS = {
    "explain",
    "memory_estimate",
    "rank_candidates",
    "validate_profile",
}
_RUST_TYPES = {
    "CandidateInput",
    "Contribution",
    "FeatureVector",
    "GovernanceVerdict",
    "MemoryBudget",
    "MemoryEstimate",
    "MemoryEstimateRequest",
    "ProfileValidationRequest",
    "RankedBatch",
    "RankingPolicy",
    "RankingRequest",
    "ScoredCandidate",
    "WeightProfile",
}


class RankingDecisionEngineUnavailableError(RuntimeError):
    """Raised when the Rust ranking engine cannot be imported."""


def _kernel(required_attr: str):
    """Load the Rust module and verify the requested public symbol exists."""
    try:
        module = importlib.import_module(_KERNEL_MODULE)
    except ImportError as exc:
        raise RankingDecisionEngineUnavailableError(
            f"Rust kernel {_KERNEL_MODULE!r} is unavailable; no Python fallback is allowed."
        ) from exc
    if not hasattr(module, required_attr):
        raise RankingDecisionEngineUnavailableError(
            f"Rust kernel {_KERNEL_MODULE!r} is missing {required_attr!r}; "
            "no Python fallback is allowed."
        )
    return module


def rank_candidates(request: Any) -> Any:
    """Delegate live ranking to Rust."""
    return _kernel("rank_candidates").rank_candidates(request)


def validate_profile(profile: Any) -> Any:
    """Delegate weight-profile validation to Rust."""
    return _kernel("validate_profile").validate_profile(profile)


def memory_estimate(request: Any) -> Any:
    """Delegate memory-budget checks to Rust."""
    return _kernel("memory_estimate").memory_estimate(request)


def explain(decision_id: Any) -> Any:
    """Delegate decision explanation lookup to Rust."""
    return _kernel("explain").explain(decision_id)


def __getattr__(name: str) -> Any:
    """Expose Rust record classes while keeping unknown names as errors."""
    if name in _FUNCTIONS:
        return globals()[name]
    if name in _RUST_TYPES:
        return getattr(_kernel(name), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
