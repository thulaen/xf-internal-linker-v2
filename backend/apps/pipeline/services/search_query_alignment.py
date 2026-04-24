"""FR-105 Reverse Search-Query Vocabulary Alignment (RSQVA).

Computes TF-IDF cosine similarity between the host's GSC query vocabulary
and the destination's GSC query vocabulary. Pages that rank for the same
search queries are topically related from the user-intent perspective,
even if their body embeddings differ.

Sources:
- Salton, G. & Buckley, C. (1988). "Term-weighting approaches in automatic
  text retrieval." IP&M 24(5):513–523, DOI 10.1016/0306-4573(88)90021-0.
  §3 TF-IDF weighting; §4 cosine similarity.
- Järvelin, K. & Kekäläinen, J. (2002). "Cumulated gain-based evaluation
  of IR techniques." ACM TOIS 20(4):422–446, DOI 10.1145/582415.582418.
  §2.1 click-weighted cumulative gain (used to weight GSC queries by
  clicks rather than raw occurrence count).

Per-page TF-IDF vectors are built daily by analytics.tasks.refresh_gsc_
query_tfidf (deferred to follow-up session) and stored in
ContentItem.gsc_query_tfidf_vector as a 1024-dim L2-normalized pgvector.

Full spec: docs/specs/fr105-reverse-search-query-vocabulary-alignment.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, TypeAlias

import numpy as np

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class RSQVASettings:
    enabled: bool = True
    ranking_weight: float = 0.05
    min_queries_per_page: int = 5
    min_query_clicks: int = 1
    max_vocab_size: int = 10000
    # BLC §6.4 minimum-data floor: need at least 7 days of GSC data.
    min_gsc_days: int = 7


@dataclass(frozen=True, slots=True)
class RSQVAEvaluation:
    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryTFIDFCache:
    """Per-pipeline-run precompute for RSQVA.

    - page_vectors: host/dest key -> L2-normalized TF-IDF vector (numpy array)
                    Fetched from ContentItem.gsc_query_tfidf_vector pgvector col
    - page_query_counts: page key -> count of distinct GSC queries
    - gsc_days_available: rolling window of available GSC data
    """

    page_vectors: Mapping[ContentKey, np.ndarray]
    page_query_counts: Mapping[ContentKey, int]
    gsc_days_available: int


def evaluate_rsqva(
    *,
    host_key: ContentKey,
    destination_key: ContentKey,
    query_cache: QueryTFIDFCache | None,
    settings: RSQVASettings,
) -> RSQVAEvaluation:
    """Compute per-pair cosine similarity on GSC-query TF-IDF vectors."""
    if not settings.enabled:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={"fallback_triggered": True, "diagnostic": "disabled", "path": "python"},
        )

    if query_cache is None:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "vector_not_computed",
                "path": "python",
            },
        )

    if query_cache.gsc_days_available < settings.min_gsc_days:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_gsc_data",
                "gsc_days_available": query_cache.gsc_days_available,
                "min_required": settings.min_gsc_days,
                "path": "python",
            },
        )

    host_qc = int(query_cache.page_query_counts.get(host_key, 0))
    dest_qc = int(query_cache.page_query_counts.get(destination_key, 0))
    if host_qc < settings.min_queries_per_page or dest_qc < settings.min_queries_per_page:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_queries_per_page",
                "host_query_count": host_qc,
                "dest_query_count": dest_qc,
                "min_required": settings.min_queries_per_page,
                "path": "python",
            },
        )

    host_vec = query_cache.page_vectors.get(host_key)
    dest_vec = query_cache.page_vectors.get(destination_key)
    if host_vec is None or dest_vec is None:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "vector_not_computed",
                "path": "python",
            },
        )

    # Both vectors should already be L2-normalized by the refresh task.
    # Check norms defensively; if near zero, fall back.
    host_norm = float(np.linalg.norm(host_vec))
    dest_norm = float(np.linalg.norm(dest_vec))
    if host_norm < 1e-9 or dest_norm < 1e-9:
        return RSQVAEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "zero_vector_norm",
                "host_norm": host_norm,
                "dest_norm": dest_norm,
                "path": "python",
            },
        )

    # Source: Salton & Buckley 1988 §4 — cosine similarity on TF-IDF vectors.
    # Since vectors are pre-normalized, dot product = cosine.
    cosine = float(np.dot(host_vec, dest_vec))
    # Numerical guard — floating-point drift can push outside [-1, 1].
    cosine = max(-1.0, min(1.0, cosine))
    # Negative cosines on TF-IDF with non-negative weights are impossible,
    # but guard defensively: clamp to [0, 1].
    score_component = max(0.0, cosine)

    return RSQVAEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "cosine_similarity": round(cosine, 6),
            "host_query_count": host_qc,
            "dest_query_count": dest_qc,
            "path": "python",
        },
    )
