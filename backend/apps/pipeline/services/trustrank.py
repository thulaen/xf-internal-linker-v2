"""TrustRank — trust propagation from curated seed pages (Gyöngyi 2004).

Reference
---------
Gyöngyi, Z., Garcia-Molina, H. & Pedersen, J. (2004). "Combating web
spam with TrustRank." *Proceedings of the 30th VLDB Conference*,
pp. 576-587.

Goal
----
Trust is scarce — a human editor can only vouch for a small seed set
of pages — but linkable across the graph: if a trusted page links to
another page, some of that trust rubs off. TrustRank formalises the
rub-off as a personalised PageRank biased toward the seeds:

    TR = (1 - d) * s + d * M^T TR

where ``s`` is the teleport distribution (uniform over trusted
seeds, zero elsewhere) and ``M`` is the column-normalised adjacency
matrix. Non-seed pages receive score only when a path of links
propagates trust from a seed to them — spam pages, typically
isolated or mutually-linked in link farms, end up with ~0 score.

Why a separate module from :mod:`personalized_pagerank`?
  Mathematically it's the same recurrence, but TrustRank has
  distinct calling semantics: the seeds come from a curated
  trust list (operator-maintained or auto-seeded by
  :mod:`trustrank_auto_seeder`), not from topic tagging. Keeping
  the two modules apart means the spam-mitigation intent shows up
  in imports (`from ... import trustrank`), and we can evolve
  either side without coupling.

In practice this module delegates the heavy-lift to
:func:`personalized_pagerank.compute` — the seed dict is built here,
the math is shared. No numerical duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable

import networkx as nx

from apps.pipeline.services.personalized_pagerank import (
    DEFAULT_DAMPING,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_TOLERANCE,
    compute as personalized_pagerank,
)


@dataclass(frozen=True)
class TrustRankScores:
    """TrustRank score distribution + the seed set that produced it."""

    scores: dict[Hashable, float]
    seed_nodes: frozenset[Hashable]

    #: Cho-GM style reason field so operators can tell why a score
    #: vector came out the way it did (e.g. "no seeds → uniform
    #: fallback" vs "3 seeds → propagated").
    reason: str


def compute(
    graph: nx.DiGraph,
    *,
    trusted_seeds: Iterable[Hashable],
    damping: float = DEFAULT_DAMPING,
    tolerance: float = DEFAULT_TOLERANCE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> TrustRankScores:
    """Return TrustRank scores for every node in *graph*.

    Parameters
    ----------
    graph
        Directed graph. Edges should point *from* a citing page *to*
        the cited page, matching the "A trusts B because A links to
        B" reading of the original paper.
    trusted_seeds
        Hand-curated or auto-seeded trust sources.
    damping, tolerance, max_iterations
        Forwarded to :func:`personalized_pagerank.compute`.

    Output is always a well-defined score dict; when there are no
    usable seeds, the helper falls back to un-personalised PageRank
    and sets :attr:`TrustRankScores.reason` so the caller can log it.
    """
    if graph.number_of_nodes() == 0:
        return TrustRankScores(
            scores={},
            seed_nodes=frozenset(),
            reason="empty_graph",
        )

    seed_set = {s for s in trusted_seeds if graph.has_node(s)}
    if not seed_set:
        reason = "no_trusted_seeds_fallback_uniform"
    else:
        reason = "trust_propagated_from_seeds"

    ppr = personalized_pagerank(
        graph,
        seeds=seed_set,
        damping=damping,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
    return TrustRankScores(
        scores=ppr.scores,
        seed_nodes=ppr.seed_nodes,
        reason=reason,
    )
