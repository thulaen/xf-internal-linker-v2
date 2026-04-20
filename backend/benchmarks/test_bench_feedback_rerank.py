"""Benchmarks for FeedbackRerankService Python path (FR-013).

Measures the rerank_candidates() fallback path (Python only, no C++ extension)
for small / medium / large candidate batches.

Run with:
    pytest backend/benchmarks/test_bench_feedback_rerank.py --benchmark-only

Django settings must be reachable. Run from the backend/ directory or with
DJANGO_SETTINGS_MODULE=config.settings.development in the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Django setup ─────────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

# Ensure extensions dir is on path (mirrors benchmarks/conftest.py)
_ext_dir = str(Path(__file__).resolve().parent.parent / "extensions")
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

import django  # noqa: E402

django.setup()

# ── Imports after Django setup ────────────────────────────────────────────────
import pytest  # noqa: E402

from apps.pipeline.services.feedback_rerank import (  # noqa: E402
    FeedbackRerankService,
    FeedbackRerankSettings,
)
from apps.pipeline.services.ranker import ScoredCandidate  # noqa: E402
import apps.pipeline.services.feedback_rerank as _fr_mod  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_service(n: int) -> FeedbackRerankService:
    """Build a service with n pre-populated pair stats (no DB access)."""
    svc = FeedbackRerankService(
        FeedbackRerankSettings(
            enabled=True,
            ranking_weight=0.2,
            exploration_rate=1.0,
            alpha_prior=1.0,
            beta_prior=1.0,
        )
    )
    for i in range(n):
        svc._pair_stats[(i, i + 1)] = {
            "total": 50,
            "successes": 30,
            "presented": 50,
            "generated": 50,
            "observation_confidence": 0.6,
        }
    svc._global_total_samples = n * 50
    return svc


def _make_candidates(n: int) -> list[ScoredCandidate]:
    """Build n minimal ScoredCandidate instances (no DB access)."""
    return [
        ScoredCandidate(
            destination_content_id=i + 1,
            destination_content_type="thread",
            host_content_id=i,
            host_content_type="thread",
            host_sentence_id=1,
            score_semantic=0.5,
            score_keyword=0.2,
            score_node_affinity=0.1,
            score_quality=0.5,
            score_silo_affinity=0.0,
            score_phrase_relevance=0.5,
            score_learned_anchor_corroboration=0.5,
            score_rare_term_propagation=0.5,
            score_field_aware_relevance=0.5,
            score_ga4_gsc=0.5,
            score_click_distance=0.5,
            score_explore_exploit=0.0,
            score_cluster_suppression=0.0,
            score_final=1.0,
            anchor_phrase="test anchor",
            anchor_start=0,
            anchor_end=11,
            anchor_confidence="strong",
            phrase_match_diagnostics={},
            learned_anchor_diagnostics={},
            rare_term_diagnostics={},
            field_aware_diagnostics={},
            cluster_diagnostics={},
            explore_exploit_diagnostics={},
            click_distance_diagnostics={},
        )
        for i in range(n)
    ]


def _host_map(n: int) -> dict[int, int]:
    return {i: i for i in range(n)}


def _dest_map(n: int) -> dict[int, int]:
    return {i + 1: i + 1 for i in range(n)}


# ── Benchmarks ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [10, 100, 500])
def test_bench_rerank_candidates_python_path(benchmark, n):
    """Benchmark FeedbackRerankService.rerank_candidates() Python fallback for N pairs.

    Covers the hot path exercised when the C++ extension is unavailable.
    Three input sizes: 10 (small), 100 (medium), 500 (large).
    """
    svc = _make_service(n)
    candidates = _make_candidates(n)
    host_map = _host_map(n)
    dest_map = _dest_map(n)

    # Force Python fallback path regardless of whether C++ extension is compiled.
    original_has_cpp = _fr_mod.HAS_CPP_EXT
    _fr_mod.HAS_CPP_EXT = False
    try:
        benchmark(svc.rerank_candidates, candidates, host_map, dest_map)
    finally:
        _fr_mod.HAS_CPP_EXT = original_has_cpp
