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

import math
import time
from contextlib import contextmanager
from collections.abc import Iterator, Mapping, Sequence

from apps.observability.instruments import safe_inc, safe_observe, safe_set
from apps.observability.api import get_metric

CORE_RANKING_COMPONENT_SIGNALS: tuple[str, ...] = (
    "semantic",
    "keyword",
    "node_affinity",
    "quality",
    "weighted_authority",
    "link_freshness",
    "phrase_relevance",
    "learned_anchor",
    "rare_term",
    "field_aware",
    "ga4_gsc",
    "click_distance",
    "anchor_diversity",
    "keyword_stuffing",
    "link_farm",
)

_MAX_REASON_LENGTH = 64
_NO_CHANGE_EPSILON = 1e-9


@contextmanager
def ranking_latency_timer(
    candidate_count: int = 0,
    *,
    path: str = "rank_candidates",
) -> Iterator[None]:
    """Time one ranking batch and emit legacy plus decision-engine metrics.

    Usage::

        with ranking_latency_timer(candidate_count=len(candidates)):
            result = rank_candidates(request)
    """
    started = time.perf_counter()
    status = "success"
    try:
        yield
    except TimeoutError:
        status = "timeout"
        observe_ranking_timeout(path)
        observe_ranking_batch_failure(path, "timeout")
        raise
    except Exception as exc:
        status = "failure"
        observe_ranking_batch_failure(path, _exception_reason(exc))
        raise
    finally:
        elapsed = time.perf_counter() - started
        safe_observe(get_metric("xf_scoring_latency_seconds"), elapsed)
        safe_observe(
            get_metric("xf_ranking_decision_latency_seconds"),
            elapsed,
            path=path,
        )
        safe_inc(get_metric("xf_ranking_batches_total"), path=path, status=status)
        if candidate_count > 0:
            safe_observe(get_metric("xf_index_candidate_count"), float(candidate_count))
            safe_observe(
                get_metric("xf_ranking_batch_size"),
                float(candidate_count),
                path=path,
            )
            safe_set(
                get_metric("xf_ranking_decision_last_batch_size"),
                float(candidate_count),
                path=path,
            )


def observe_ranking_batch_failure(path: str, reason: str) -> None:
    """Increment the ranking batch failure counter with bounded labels."""
    safe_inc(
        get_metric("xf_ranking_batch_failures_total"),
        path=path,
        reason=_normalise_reason(reason),
    )


def observe_ranking_timeout(path: str) -> None:
    """Increment the ranking timeout counter for the affected path."""
    safe_inc(get_metric("xf_ranking_batch_timeouts_total"), path=path)


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


def observe_component_batch(
    component_scores: Sequence[Sequence[float]],
    weights: Sequence[float],
    silo_scores: Sequence[float],
    signal_names: Sequence[str] = CORE_RANKING_COMPONENT_SIGNALS,
) -> None:
    """Emit raw and weighted contribution metrics for the core Rust batch.

    Labels are limited to the fixed signal-name list so this stays safe for
    VictoriaMetrics cardinality while still showing per-signal trends.
    """
    for row_index, row in enumerate(component_scores):
        contributions: dict[str, float] = {}
        raw_scores: dict[str, float] = {}
        for index, name in enumerate(signal_names):
            if index >= len(row) or index >= len(weights):
                continue
            raw = _finite_float(row[index])
            contribution = raw * _finite_float(weights[index])
            raw_scores[name] = raw
            contributions[name] = contribution
        if row_index < len(silo_scores):
            contributions["silo_affinity"] = _finite_float(silo_scores[row_index])
        observe_signal_contributions(contributions, raw_scores=raw_scores)


def observe_signal_contributions(
    contributions: Mapping[str, float],
    *,
    raw_scores: Mapping[str, float] | None = None,
) -> None:
    """Emit per-signal contribution and dominant-change counters."""
    strongest_signal = ""
    strongest_value = 0.0
    for signal, value in contributions.items():
        numeric = _finite_float(value)
        direction = _direction(numeric)
        safe_observe(
            get_metric("xf_ranking_signal_contribution"),
            numeric,
            signal=signal,
            direction=direction,
        )
        safe_set(
            get_metric("xf_ranking_signal_last_contribution"),
            numeric,
            signal=signal,
        )
        if abs(numeric) > abs(strongest_value):
            strongest_signal = signal
            strongest_value = numeric
    for signal, raw in (raw_scores or {}).items():
        safe_observe(
            get_metric("xf_ranking_signal_raw_score"),
            _finite_float(raw),
            signal=signal,
        )
    if strongest_signal and abs(strongest_value) > _NO_CHANGE_EPSILON:
        safe_inc(
            get_metric("xf_ranking_score_change_total"),
            driver=strongest_signal,
            direction=_direction(strongest_value),
        )


def _direction(value: float) -> str:
    if value > _NO_CHANGE_EPSILON:
        return "positive"
    if value < -_NO_CHANGE_EPSILON:
        return "negative"
    return "neutral"


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "value_error"
    if exc.__class__.__name__ == "KernelUnavailableError":
        return "kernel_unavailable"
    return _normalise_reason(exc.__class__.__name__ or "other")


def _normalise_reason(reason: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in reason.lower())
    return (safe or "other")[:_MAX_REASON_LENGTH]


def _finite_float(value: float) -> float:
    number = float(value)
    return number if math.isfinite(number) else 0.0
