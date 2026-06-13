"""Ranking-engine instrumentation helpers.

Wires real call-site measurements into the metrics registry for the
Rust ranking-decision engine and the Python score_destination_matches
path. Every function here is a thin wrapper that calls instruments.py
helpers — no logic, no fallback paths of our own.

Call sites
----------
- apps.pipeline.services.ranking_decision_engine.rank_candidates
  (Rust hot path — Python boundary wraps it)
- apps.pipeline.services.ranker.score_destination_matches
  (Python composite scoring per destination)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Iterator

from apps.observability.instruments import safe_inc, safe_observe
from apps.observability.api import get_metric


@contextmanager
def ranking_latency_timer(candidate_count: int = 0) -> Iterator[None]:
    """Context manager: times one ranking batch and emits xf_scoring_latency_seconds.

    Usage::

        with ranking_latency_timer(candidate_count=len(candidates)):
            result = rank_candidates(request)
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        safe_observe(get_metric("xf_scoring_latency_seconds"), elapsed)
        if candidate_count > 0:
            safe_observe(get_metric("xf_index_candidate_count"), float(candidate_count))


def observe_ranking_validation_failure(reason: str) -> None:
    """Increment the governance/validation failure counter.

    Emits xf_scoring_rejected_total{reason=<reason>}.  Call this when the
    Rust ranking engine returns a GovernanceVerdict that rejects a candidate,
    or when validate_profile raises.
    """
    safe_inc(get_metric("xf_scoring_rejected_total"), reason=reason)


def observe_ranked_scores(scores: list[float]) -> None:
    """Emit xf_scoring_score observations for each final composite score.

    Pass the list of score_final values produced by score_destination_matches
    so the histogram captures the score distribution over time.
    """
    metric = get_metric("xf_scoring_score")
    for s in scores:
        safe_observe(metric, float(s))
