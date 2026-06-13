"""Python boundary for the Rust RankingDecisionEngine.

The Rust PyO3 module ``extensions.ranking_decision_engine`` owns ranking
decisions. This file intentionally contains no Python scoring fallback; it only
loads the Rust module and delegates calls.

Instrumentation (2026-06-13)
-----------------------------
rank_candidates is timed via ranking_latency_timer so
xf_scoring_latency_seconds and xf_index_candidate_count receive real data
on every ranking pass. validate_profile failures increment
xf_scoring_rejected_total{reason="governance_validation_failure"}.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

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
    """Delegate live ranking to Rust. Times the call and records candidate count."""
    try:
        from apps.observability.metrics_ranking import ranking_latency_timer
        candidate_count = len(getattr(request, "candidates", []))
        with ranking_latency_timer(candidate_count=candidate_count):
            return _kernel("rank_candidates").rank_candidates(request)
    except ImportError:
        # observability module not yet available (e.g. during first-boot
        # before migrations run). Fall through to unmonitored call.
        logger.debug("ranking_latency_timer unavailable — metrics skipped")
        return _kernel("rank_candidates").rank_candidates(request)


def validate_profile(profile: Any) -> Any:
    """Delegate weight-profile validation to Rust.

    A failed validation increments xf_scoring_rejected_total so
    the RankingValidationFailures alert fires when the Rust engine
    rejects governance checks.
    """
    try:
        result = _kernel("validate_profile").validate_profile(profile)
    except Exception as exc:
        try:
            from apps.observability.metrics_ranking import observe_ranking_validation_failure
            observe_ranking_validation_failure("governance_validation_failure")
        except ImportError:
            pass
        raise exc from exc
    # Surface governance rejections that come back as structured verdicts
    # rather than exceptions (Rust may return a verdict with rejected=True).
    is_rejected = getattr(result, "rejected", False) or getattr(result, "failed", False)
    if is_rejected:
        try:
            from apps.observability.metrics_ranking import observe_ranking_validation_failure
            reason = str(getattr(result, "reason", "governance_validation_failure"))
            observe_ranking_validation_failure(reason[:64])
        except ImportError:
            pass
    return result


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
