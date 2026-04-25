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

    PR_personalised(v) = (1 - alpha) * p(v)
                      + alpha * Σ_{u → v} PR(u) / outdeg(u)

where ``p(v)`` is the personalisation distribution (uniform over the
seed set, zero elsewhere) instead of ``1/N`` everywhere.

Haveliwala's key result: a handful of topic-specific PageRank vectors
can be precomputed offline, then linearly blended at query time to
emulate arbitrary topic mixes — useful for the linker since the
same pre-computed vectors power both "recommend similar posts to
X" and "surface topical authorities for query Q".

Phase 5b: the numerical inner loop now runs through the C++ kernel
:func:`extensions.pagerank.personalized_pagerank_step` (Phase 5a).
Power-iterates from a uniform start to convergence with the same
``tol`` / ``max_iter`` semantics ``networkx.pagerank`` had, but at
the speed of the existing PageRank C++ kernel. The kernel uses
this codebase's convention where ``damping`` is the **teleport
probability** (textbook ``1 - alpha``); the wrapper converts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Hashable, Iterable, Mapping

import networkx as nx
import numpy as np

from .graph_csr_utils import nx_digraph_to_csr

logger = logging.getLogger(__name__)


#: Damping factor (link-following probability — networkx convention).
#: 0.85 is the Page-Brin-Haveliwala consensus value; lower values
#: bias more toward the seed set, higher values emphasise graph
#: structure. The C++ kernel uses ``1 - damping`` internally.
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

    # Build the per-node personalisation vector. Empty / invalid seed
    # sets fall through to uniform 1/N, matching the prior behaviour
    # when ``personalization=None`` was passed to networkx.
    csr = nx_digraph_to_csr(graph, normalize_per_source=True)
    n = csr.node_count
    if n == 0:
        return PersonalizedPageRankScores(scores={}, seed_nodes=frozenset())

    personalization = np.full(n, 1.0 / n, dtype=np.float64)
    if seed_set:
        if seed_weights is None:
            weight_per_seed = 1.0 / len(seed_set)
            personalization = np.zeros(n, dtype=np.float64)
            for seed in seed_set:
                personalization[csr.index_for[seed]] = weight_per_seed
        else:
            raw = {s: float(seed_weights.get(s, 0.0)) for s in seed_set}
            total = sum(raw.values())
            if total <= 0.0:
                # All-zero weights → degenerate; fall back to uniform
                # over the seed set, same as the no-weights branch.
                weight_per_seed = 1.0 / len(seed_set)
                personalization = np.zeros(n, dtype=np.float64)
                for seed in seed_set:
                    personalization[csr.index_for[seed]] = weight_per_seed
            else:
                personalization = np.zeros(n, dtype=np.float64)
                for seed, weight in raw.items():
                    personalization[csr.index_for[seed]] = weight / total

    # Convert from networkx's "alpha" (link-following probability) to
    # this codebase's "damping" (teleport probability) — see the
    # pagerank_core.h header comment for the convention.
    teleport_probability = 1.0 - damping

    # Phase 5b — drive the C++ kernel's power iteration to convergence.
    # Same loop shape ``weighted_pagerank.run_weighted_pagerank`` uses
    # for the uniform variant.
    from extensions import pagerank as pagerank_kernel  # local import

    ranks = np.full(n, 1.0 / n, dtype=np.float64)
    for _iteration in range(max_iterations):
        next_ranks, delta = pagerank_kernel.personalized_pagerank_step(
            csr.indptr,
            csr.indices,
            csr.data,
            ranks,
            csr.dangling,
            personalization,
            teleport_probability,
            n,
        )
        ranks = next_ranks
        if delta <= n * tolerance:
            break

    scores = {csr.node_keys[i]: float(ranks[i]) for i in range(n)}
    return PersonalizedPageRankScores(
        scores=scores,
        seed_nodes=frozenset(seed_set),
    )
