"""Inverse-PageRank Auto-Seeder for TrustRank (Gyöngyi 2004 §4.1).

Reference
---------
Gyöngyi, Z., Garcia-Molina, H. & Pedersen, J. (2004). "Combating web
spam with TrustRank." *VLDB*, §4.1 — "Seed Selection via Inverse
PageRank."

Goal
----
TrustRank's quality depends on picking trusted seeds that have wide
reach — pages whose trust, once injected, propagates to the most of
the rest of the graph. Gyöngyi et al. observe that **pages with high
out-PageRank** fit this bill: they link to a broad slice of the
graph, so trust propagated from them reaches many other pages in
few steps.

Concretely: reverse every edge and run PageRank on the reversed
graph. The top-ranked nodes in that reversed PageRank are the best
seed candidates. The paper calls this "Inverse PageRank."

The linker adds two on top of that raw signal:

- **Quality filters** — reject candidates flagged by META-25
  spam_guard, below META-20 post_quality, or above the readability
  grade ceiling (spec pick #19). Even a high-reach page is a bad
  seed if it's itself low-quality.
- **Fallback** — if the filtered candidate pool is smaller than K,
  top up with the best remaining forward-PageRank nodes.

The module is pure Python + networkx; no DB access. A scheduled
job (``trustrank_auto_seeder`` in the 13:00–23:00 runner) supplies
the graph and the per-node quality map; this module returns the
seed list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping

import networkx as nx


#: Size of the initial candidate pool before quality filtering. The
#: plan's ``trustrank_auto_seeder.candidate_pool_size`` default is
#: 100; we mirror that so AppSetting and this module agree.
DEFAULT_CANDIDATE_POOL_SIZE: int = 100

#: Number of seeds to keep after filtering. Matches the plan's
#: ``trustrank_auto_seeder.seed_count_k`` default.
DEFAULT_SEED_COUNT_K: int = 20

#: Default post-quality floor — entities below this are rejected.
DEFAULT_POST_QUALITY_MIN: float = 0.6

#: Default readability ceiling (Flesch-Kincaid grade). Rejecting
#: above this keeps the seed list out of gibberish / jargon-heavy
#: pages.
DEFAULT_READABILITY_GRADE_MAX: float = 16.0


@dataclass(frozen=True)
class AutoSeedResult:
    """Seed-picker output with audit trail for operators."""

    seeds: list[Hashable]
    fallback_used: bool
    rejected_count: int
    reason: str


def pick_seeds(
    graph: nx.DiGraph,
    *,
    candidate_pool_size: int = DEFAULT_CANDIDATE_POOL_SIZE,
    seed_count_k: int = DEFAULT_SEED_COUNT_K,
    spam_flagged: set[Hashable] | None = None,
    post_quality: Mapping[Hashable, float] | None = None,
    post_quality_min: float = DEFAULT_POST_QUALITY_MIN,
    readability_grade: Mapping[Hashable, float] | None = None,
    readability_grade_max: float = DEFAULT_READABILITY_GRADE_MAX,
) -> AutoSeedResult:
    """Return up to *seed_count_k* TrustRank seeds picked from *graph*.

    Selection pipeline:

    1. Rank all nodes by **inverse PageRank** (PageRank on the
       edge-reversed graph). Keep the top *candidate_pool_size*.
    2. Drop candidates in ``spam_flagged``.
    3. Drop candidates whose ``post_quality[node] < post_quality_min``
       (only applied when a mapping is provided — nodes missing
       from the mapping pass through on the principle that we only
       reject on affirmative evidence of low quality).
    4. Drop candidates whose ``readability_grade[node] >
       readability_grade_max``.
    5. Keep the top *seed_count_k* survivors. If fewer survive, top
       up from the best remaining forward-PageRank nodes (fallback)
       and flag ``fallback_used=True``.

    Empty graph → empty result with ``reason="empty_graph"``.
    """
    if not graph.is_directed():
        raise ValueError("auto-seeder requires a directed graph")
    if candidate_pool_size <= 0 or seed_count_k <= 0:
        raise ValueError("candidate_pool_size and seed_count_k must be > 0")
    if graph.number_of_nodes() == 0:
        return AutoSeedResult(
            seeds=[],
            fallback_used=False,
            rejected_count=0,
            reason="empty_graph",
        )

    spam = spam_flagged or set()

    # 1. Inverse PageRank.
    inverse_pr = nx.pagerank(graph.reverse(copy=False))
    candidates = sorted(
        inverse_pr.items(), key=lambda pair: (-pair[1], str(pair[0]))
    )[:candidate_pool_size]

    survivors: list[Hashable] = []
    rejected = 0
    for node, _ in candidates:
        if node in spam:
            rejected += 1
            continue
        if post_quality is not None and node in post_quality:
            if post_quality[node] < post_quality_min:
                rejected += 1
                continue
        if readability_grade is not None and node in readability_grade:
            if readability_grade[node] > readability_grade_max:
                rejected += 1
                continue
        survivors.append(node)
        if len(survivors) >= seed_count_k:
            break

    if len(survivors) >= seed_count_k:
        return AutoSeedResult(
            seeds=survivors[:seed_count_k],
            fallback_used=False,
            rejected_count=rejected,
            reason="filtered_inverse_pagerank",
        )

    # 5. Fallback — fill the deficit with top forward-PageRank nodes
    # that haven't already been kept, bypassing the quality filter.
    # Operator policy: a partial filtered list + fallback is better
    # than an empty seed set, which would leave TrustRank un-anchored.
    forward_pr = nx.pagerank(graph)
    forward_ranked = sorted(
        forward_pr.items(), key=lambda pair: (-pair[1], str(pair[0]))
    )
    existing = set(survivors)
    for node, _ in forward_ranked:
        if node in existing:
            continue
        survivors.append(node)
        existing.add(node)
        if len(survivors) >= seed_count_k:
            break

    return AutoSeedResult(
        seeds=survivors,
        fallback_used=True,
        rejected_count=rejected,
        reason="fallback_to_top_k_by_pagerank",
    )
