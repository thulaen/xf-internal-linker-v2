"""FR-015 Final Slate Diversity Reranking.

Implements Maximal Marginal Relevance (MMR) greedy selection for
per-host-thread destination slate diversity.

The algorithm reranks the candidates available for a single host thread
so the final k selected destinations are both relevant AND varied.

Sources:
  - Carbonell & Goldstein, SIGIR 1998 — "The Use of MMR, Diversity-Based
    Reranking for Reordering Documents and Producing Summaries"
    https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf
  - Patent US20070294225A1 (Radlinski, Dumais, Horvitz — Microsoft)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from apps.suggestions.recommended_weights import recommended_bool, recommended_float

if TYPE_CHECKING:
    from .ranker import ContentKey, ScoredCandidate

try:
    from extensions import feedrerank

    HAS_CPP_DIVERSITY = hasattr(feedrerank, "calculate_mmr_scores_batch")
except ImportError:
    feedrerank = None
    HAS_CPP_DIVERSITY = False


@dataclass(frozen=True, slots=True)
class SlateDiversitySettings:
    """Settings controlling the final slate diversity reranker."""

    enabled: bool = recommended_bool("slate_diversity.enabled")
    diversity_lambda: float = recommended_float(
        "slate_diversity.diversity_lambda"
    )  # 1.0 = pure relevance, 0.0 = pure diversity
    score_window: float = recommended_float(
        "slate_diversity.score_window"
    )  # max score gap from top candidate to be eligible
    similarity_cap: float = recommended_float(
        "slate_diversity.similarity_cap"
    )  # cosine similarity above which items are flagged as redundant
    algorithm_version: str = "fr015-v1"


def apply_slate_diversity(
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]],
    embedding_lookup: dict[ContentKey, np.ndarray],
    settings: SlateDiversitySettings,
    max_per_host: int = 3,
) -> list[ScoredCandidate]:
    """Select the final slate of suggestions using per-host MMR diversity.

    This replaces the flat top-k selection with a diversity-aware pass:
    for each host thread, up to max_per_host destinations are chosen such
    that they are both high-scoring and semantically varied.

    When disabled, falls back to simple top-1-per-destination ordering
    (callers should use select_final_candidates instead).

    Args:
        candidates_by_destination: mapping of destination_key -> sorted candidates
        embedding_lookup: mapping of content_item_id -> L2-normalised embedding
        settings: diversity settings
        max_per_host: maximum suggestions per host thread

    Returns:
        Flat list of selected ScoredCandidate objects with diversity scores set.
    """
    # Build host-keyed reverse index: host_key -> all candidates for that host
    host_to_candidates: dict[ContentKey, list[ScoredCandidate]] = defaultdict(list)
    for dest_candidates in candidates_by_destination.values():
        for c in dest_candidates:
            host_to_candidates[c.host_key].append(c)

    for host_key in host_to_candidates:
        host_to_candidates[host_key].sort(
            key=lambda c: (-c.score_final, -c.score_semantic)
        )

    # Process hosts in priority order (highest best-candidate score first)
    ordered_hosts = sorted(
        host_to_candidates.items(),
        key=lambda item: -item[1][0].score_final if item[1] else 0.0,
    )

    claimed: set[ContentKey] = set()
    selected_directions: set[tuple[ContentKey, ContentKey]] = set()
    result: list[ScoredCandidate] = []

    for host_key, host_candidates in ordered_hosts:
        if not host_candidates:
            continue

        selected = _mmr_select_for_host(
            host_candidates=host_candidates,
            embedding_lookup=embedding_lookup,
            settings=settings,
            k=max_per_host,
            claimed=claimed,
            selected_directions=selected_directions,
        )

        for c in selected:
            claimed.add(c.destination_key)
            selected_directions.add((c.destination_key, c.host_key))

        result.extend(selected)

    return sorted(
        result,
        key=lambda c: (
            c.host_content_id,
            c.host_content_type,
            c.slate_diversity_diagnostics.get("slot", 999),
            -c.score_final,
            -c.score_semantic,
        ),
    )


def _mmr_select_for_host(
    host_candidates: list[ScoredCandidate],
    embedding_lookup: dict[ContentKey, np.ndarray],
    settings: SlateDiversitySettings,
    k: int,
    claimed: set[ContentKey],
    selected_directions: set[tuple[ContentKey, ContentKey]],
) -> list[ScoredCandidate]:
    """Greedy MMR selection for a single host thread's destination slate.

    MMR formula (Carbonell & Goldstein 1998):
      MMR(Di) = λ · relevance(Di)  −  (1 − λ) · max_j∈S [ cosine(Di, Dj) ]

    Where:
      Di       = candidate not yet in slate S
      relevance = normalized score_final within the eligible window
      cosine   = dot product of L2-normalised destination embeddings
      λ        = diversity_lambda (higher = more relevance weight)
    """
    # Filter: skip already-claimed destinations and circular pairs
    eligible = [
        c
        for c in host_candidates
        if c.destination_key not in claimed
        and (c.host_key, c.destination_key) not in selected_directions
    ]
    if not eligible:
        return []

    # Apply score window: only candidates within score_window of the top are eligible
    top_score = eligible[0].score_final
    bottom_score = eligible[-1].score_final
    score_range = (top_score - bottom_score) if top_score != bottom_score else 1.0

    window_pool = [
        c for c in eligible if (top_score - c.score_final) <= settings.score_window
    ]
    fallback_pool = [c for c in eligible if c not in window_pool]

    def normalize(score: float) -> float:
        return (score - bottom_score) / score_range

    selected: list[ScoredCandidate] = []
    selected_embeddings: list[np.ndarray] = []
    runtime_status = get_slate_diversity_runtime_status()
    runtime_path = runtime_status["path"]
    runtime_reason = runtime_status["reason"]

    for slot_idx in range(k):
        pool = window_pool if window_pool else fallback_pool
        if not pool:
            break

        if not selected_embeddings:
            # First slot: highest score_final, no diversity penalty yet
            pick = pool.pop(0)
            emb = embedding_lookup.get(pick.destination_key)
            diag: dict = {
                "mmr_applied": True,
                "lambda": settings.diversity_lambda,
                "score_window": settings.score_window,
                "slot": slot_idx,
                "relevance_normalized": round(normalize(pick.score_final), 4),
                "max_similarity_to_selected": None,
                "mmr_score": round(normalize(pick.score_final), 4),
                "swapped_from_rank": None,
                "window_source": "score_window"
                if pick in window_pool
                else "fallback_pool",
                "runtime_path": runtime_path,
                "runtime_reason": runtime_reason,
                "algorithm_version": settings.algorithm_version,
            }
            updated = replace(
                pick,
                score_slate_diversity=round(normalize(pick.score_final), 6),
                slate_diversity_diagnostics=diag,
            )
            selected.append(updated)
            if emb is not None:
                selected_embeddings.append(emb)

        else:
            # Subsequent slots: apply the MMR penalty
            relevance = np.asarray(
                [normalize(candidate.score_final) for candidate in pool],
                dtype=np.float64,
            )
            candidate_embeddings = np.asarray(
                [
                    embedding_lookup.get(
                        candidate.destination_key, np.zeros(0, dtype=np.float32)
                    )
                    for candidate in pool
                ],
                dtype=object,
            )
            usable_cpp = HAS_CPP_DIVERSITY and all(
                embedding.size > 0 for embedding in candidate_embeddings
            )

            if usable_cpp:
                mmr_scores, max_similarities = feedrerank.calculate_mmr_scores_batch(
                    relevance,
                    np.vstack(candidate_embeddings).astype(np.float64, copy=False),
                    np.vstack(selected_embeddings).astype(np.float64, copy=False),
                    float(settings.diversity_lambda),
                )
            else:
                mmr_scores = np.empty(len(pool), dtype=np.float64)
                max_similarities = np.empty(len(pool), dtype=np.float64)
                for i, candidate in enumerate(pool):
                    emb = embedding_lookup.get(candidate.destination_key)
                    if emb is not None and selected_embeddings:
                        sims = [
                            float(np.dot(emb, selected_emb))
                            for selected_emb in selected_embeddings
                        ]
                        max_sim = max(sims)
                    else:
                        max_sim = 0.0
                    max_similarities[i] = max_sim
                    mmr_scores[i] = (
                        settings.diversity_lambda * relevance[i]
                        - (1.0 - settings.diversity_lambda) * max_sim
                    )

            best_pool_idx = int(np.argmax(mmr_scores))
            best_pick = pool[best_pool_idx]
            best_mmr = float(mmr_scores[best_pool_idx])
            best_max_sim = float(max_similarities[best_pool_idx])
            best_original_rank = best_pool_idx

            if best_pick is None or best_pool_idx is None:
                break

            pool.pop(best_pool_idx)
            emb = embedding_lookup.get(best_pick.destination_key)
            diag = {
                "mmr_applied": True,
                "lambda": settings.diversity_lambda,
                "score_window": settings.score_window,
                "slot": slot_idx,
                "relevance_normalized": round(normalize(best_pick.score_final), 4),
                "max_similarity_to_selected": round(best_max_sim, 4),
                "mmr_score": round(best_mmr, 4),
                "swapped_from_rank": best_original_rank
                if best_original_rank > 0
                else None,
                "similarity_cap": settings.similarity_cap,
                "flagged_redundant": best_max_sim >= settings.similarity_cap,
                "window_source": "score_window"
                if pool is window_pool
                else "fallback_pool",
                "runtime_path": "cpp_extension" if usable_cpp else runtime_path,
                "runtime_reason": (
                    "Native C++ MMR kernel handled this slot."
                    if usable_cpp
                    else runtime_reason
                ),
                "algorithm_version": settings.algorithm_version,
            }
            updated = replace(
                best_pick,
                score_slate_diversity=round(best_mmr, 6),
                slate_diversity_diagnostics=diag,
            )
            selected.append(updated)
            if emb is not None:
                selected_embeddings.append(emb)

    return selected


def get_slate_diversity_runtime_status() -> dict[str, object]:
    """Return plain-English runtime status for the FR-015 fast path."""
    if HAS_CPP_DIVERSITY:
        return {
            "available": True,
            "path": "cpp_extension",
            "reason": "Native C++ MMR kernel is available for the FR-015 diversity step.",
        }
    return {
        "available": False,
        "path": "python_fallback",
        "reason": "Python fallback is active because the native C++ MMR kernel is not compiled or could not be loaded.",
    }


# ---------------------------------------------------------------------------
# FR-239 — Stage-1 MMR rerank helper (standalone, key-shape-agnostic)
# ---------------------------------------------------------------------------
#
# Distinct from `apply_slate_diversity` (FR-015) which operates on
# ``ScoredCandidate`` objects at the FINAL ranking stage. This helper
# operates on raw ``(key, score)`` tuples + an embedding lookup so it
# can be used at Stage 1 retrieval (where ``ScoredCandidate`` doesn't
# exist yet) without taking on the full ranker dependency.
#
# Sources of truth:
#   - Carbonell & Goldstein (1998), SIGIR §3 — defines MMR as
#     λ · Sim(q, d) − (1−λ) · max_{d'∈S} Sim(d, d').
#   - Drosou & Pitoura (2010) SIGMOD Record 39(1) DOI 10.1145/1860702.1860709
#     — confirms MMR remains the best practical default for diversification.
#
# Why a separate helper rather than reusing `_mmr_select_for_host`:
#   - `_mmr_select_for_host` is glued to ScoredCandidate (`replace(...)` on
#     dataclass fields, `score_final` / `score_semantic` math, slot-
#     diagnostics writes). It needs the full ranker pipeline to run.
#   - Stage-1 retrieval has only `(host_key, faiss_score)` pairs and host
#     embeddings — no ScoredCandidate yet (those don't exist until after
#     Stage 2 scoring). Forcing the existing helper to handle both shapes
#     would break its single-responsibility cleanliness.
#   - Both helpers compute the same MMR formula with the same library
#     citation; this is intentional algorithmic DRY at the math layer
#     not at the API layer.

#: Default MMR lambda for Stage-1 reranking. Carbonell & Goldstein 1998
#: Table 2 reports λ ∈ [0.3, 0.7] across their experiments; 0.7 is the
#: balanced precision/diversity setting most often cited as the safe
#: default in follow-up surveys (e.g. Drosou & Pitoura 2010 §3.1).
STAGE1_MMR_LAMBDA_DEFAULT: float = 0.7

#: Default Stage-1 overfetch multiplier. Carbonell & Goldstein 1998 §3
#: ("retrieve at least 2× to give MMR room") motivates the 2× factor.
STAGE1_OVERFETCH_MULTIPLIER_DEFAULT: int = 2


def mmr_rerank_keys(
    scored_keys: list[tuple[object, float]],
    embedding_lookup: dict[object, np.ndarray],
    *,
    k: int,
    lambda_: float = STAGE1_MMR_LAMBDA_DEFAULT,
) -> list[tuple[object, float]]:
    """MMR-rerank ``scored_keys`` to k diverse picks (Carbonell & Goldstein 1998).

    Input ``scored_keys`` are ``(key, relevance)`` ordered desc by score;
    ``embedding_lookup`` maps key → L2-unit np.ndarray (missing or zero-
    size embedding falls back to relevance-only — treated as fully
    diverse). Returns ``[(key, original_relevance), ...]`` in MMR-pick
    order. No-op short-circuit when ``len(scored_keys) <= k``.
    """
    if not scored_keys:
        return []
    if len(scored_keys) <= k:
        return list(scored_keys)

    candidates = list(scored_keys)
    selected: list[tuple[object, float]] = []
    selected_embeddings: list[np.ndarray] = []
    _append_pick(
        candidates.pop(0), selected, selected_embeddings, embedding_lookup
    )

    while len(selected) < k and candidates:
        best_idx = _pick_next_mmr_index(
            candidates=candidates,
            selected_embeddings=selected_embeddings,
            embedding_lookup=embedding_lookup,
            lambda_=lambda_,
        )
        _append_pick(
            candidates.pop(best_idx),
            selected, selected_embeddings, embedding_lookup,
        )
    return selected


def _append_pick(
    pick: tuple[object, float],
    selected: list[tuple[object, float]],
    selected_embeddings: list[np.ndarray],
    embedding_lookup: dict[object, np.ndarray],
) -> None:
    """Add a pick to the selection lists; skips zero-size embeddings."""
    selected.append(pick)
    emb = embedding_lookup.get(pick[0])
    if emb is not None and emb.size > 0:
        selected_embeddings.append(emb)


def _pick_next_mmr_index(
    *,
    candidates: list[tuple[object, float]],
    selected_embeddings: list[np.ndarray],
    embedding_lookup: dict[object, np.ndarray],
    lambda_: float,
) -> int:
    """Return the index in ``candidates`` of the next MMR pick.

    Computes ``λ·relevance − (1−λ)·max_sim_to_selected`` for each
    candidate and returns the argmax index. Carbonell & Goldstein 1998
    SIGIR §3 — exact formula. Linear in len(candidates) × len(selected).
    """
    best_idx = 0
    best_score = float("-inf")
    for idx, (key, relevance) in enumerate(candidates):
        emb = embedding_lookup.get(key)
        if emb is None or emb.size == 0 or not selected_embeddings:
            max_sim = 0.0
        else:
            max_sim = max(float(np.dot(emb, s)) for s in selected_embeddings)
        mmr_value = lambda_ * relevance - (1.0 - lambda_) * max_sim
        if mmr_value > best_score:
            best_score = mmr_value
            best_idx = idx
    return best_idx
