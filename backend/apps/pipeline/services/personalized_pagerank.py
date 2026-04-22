"""Personalized PageRank (Haveliwala 2002, WWW).

Reference
---------
Haveliwala, T. H. (2002). "Topic-sensitive PageRank." *Proceedings
of the 11th International World Wide Web Conference*, pp. 517-526.

Goal
----
Standard PageRank assigns one global score per node. Personalized
PageRank biases the random-walk teleport distribution toward a
caller-specified "seed set" — usually nodes tagged with a topic of
interest — so the resulting scores rank the graph *from that
topic's perspective*. Same recurrence, just a different teleport
vector::

    PR_personalised(v) = (1 - d) * p(v)
                      + d * Σ_{u → v} PR(u) / outdeg(u)

where ``p(v)`` is the personalisation distribution (uniform over the
seed set, zero elsewhere) instead of ``1/N`` everywhere.

Haveliwala's key result: a handful of topic-specific PageRank vectors
can be precomputed offline, then linearly blended at query time to
emulate arbitrary topic mixes — useful for the linker since the
same pre-computed vectors power both "recommend similar posts to
X" and "surface topical authorities for query Q".

This helper is a thin convenience over ``networkx.pagerank`` — the
numerical heavy-lifting is delegated. What we add:

- A validated wrapper that enforces the ``personalization`` dict
  only names nodes that exist in the graph (networkx silently
  ignores unknown keys, which masks bugs upstream).
- A :class:`PersonalizedPageRankScores` dataclass with the seed
  set retained for diagnostics.
- A helper to build the uniform-over-seeds personalisation dict
  callers usually want.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Mapping

import networkx as nx


#: Damping factor (teleport probability = 1 - damping). 0.85 is the
#: Page-Brin-Haveliwala consensus value; lower values bias more
#: toward the seed set, higher values emphasise graph structure.
DEFAULT_DAMPING: float = 0.85

#: Convergence tolerance — sum of absolute per-node changes.
DEFAULT_TOLERANCE: float = 1e-6

#: Maximum power-iteration steps. 100 is nearly always enough.
DEFAULT_MAX_ITERATIONS: int = 100


@dataclass(frozen=True)
class PersonalizedPageRankScores:
    """Per-node PPR scores plus the seed set that produced them."""

    scores: dict[Hashable, float]
    seed_nodes: frozenset[Hashable]


def build_seed_personalization(
    seeds: Iterable[Hashable],
    graph: nx.DiGraph,
) -> dict[Hashable, float]:
    """Return a uniform personalisation dict over *seeds*.

    Unknown-seed nodes are dropped (with no error) — callers often
    hand in IDs from an upstream system that may have been pruned
    since. Empty result is returned as ``{}``; callers can detect
    that and fall back to un-personalised PageRank.
    """
    seed_set = {s for s in seeds if graph.has_node(s)}
    if not seed_set:
        return {}
    weight = 1.0 / len(seed_set)
    return {seed: weight for seed in seed_set}


def compute(
    graph: nx.DiGraph,
    *,
    seeds: Iterable[Hashable],
    damping: float = DEFAULT_DAMPING,
    tolerance: float = DEFAULT_TOLERANCE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    seed_weights: Mapping[Hashable, float] | None = None,
) -> PersonalizedPageRankScores:
    """Return the PPR score distribution biased toward *seeds*.

    Parameters
    ----------
    graph
        Directed graph. Undirected input is rejected — PPR's
        teleport semantics depend on edge direction.
    seeds
        Nodes whose proximity to each other node we want to measure.
        Unknown node IDs are silently dropped.
    damping
        Usual PageRank damping factor in (0, 1).
    tolerance, max_iterations
        Forwarded to ``networkx.pagerank``.
    seed_weights
        Optional per-seed weights. Defaults to uniform over the seed
        set. Values are normalised to sum to 1.0 before use.

    Raises
    ------
    ValueError
        If the graph is undirected or if ``damping`` is outside (0, 1).
    """
    if not graph.is_directed():
        raise ValueError("Personalized PageRank requires a directed graph")
    if not 0.0 < damping < 1.0:
        raise ValueError("damping must be in (0, 1)")
    if graph.number_of_nodes() == 0:
        return PersonalizedPageRankScores(scores={}, seed_nodes=frozenset())

    seed_set = {s for s in seeds if graph.has_node(s)}
    if not seed_set:
        # Caller wants personalisation but no valid seeds — degenerate
        # to un-personalised PageRank so we still produce usable scores.
        personalisation = None
    elif seed_weights is None:
        weight = 1.0 / len(seed_set)
        personalisation = {seed: weight for seed in seed_set}
    else:
        raw = {s: float(seed_weights.get(s, 0.0)) for s in seed_set}
        total = sum(raw.values())
        if total <= 0.0:
            # All provided weights are zero → fall back to uniform.
            weight = 1.0 / len(seed_set)
            personalisation = {seed: weight for seed in seed_set}
        else:
            personalisation = {s: w / total for s, w in raw.items()}

    scores = nx.pagerank(
        graph,
        alpha=damping,
        personalization=personalisation,
        tol=tolerance,
        max_iter=max_iterations,
    )

    return PersonalizedPageRankScores(
        scores=dict(scores),
        seed_nodes=frozenset(seed_set),
    )
