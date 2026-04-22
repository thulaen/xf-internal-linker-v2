"""HITS — Hyperlink-Induced Topic Search (Kleinberg 1999).

Reference
---------
Kleinberg, J. M. (1999). "Authoritative sources in a hyperlinked
environment." *Journal of the ACM* 46(5): 604-632.

Goal
----
Assign every node in a directed graph two scores — **authority** and
**hub** — by mutual reinforcement::

    authority(v) = Σ hub(u)   for each u → v
    hub(v)       = Σ authority(w) for each v → w

Intuition: good authorities are pointed to by good hubs; good hubs
point to good authorities. After normalisation + a few dozen power
iterations, the two score vectors converge to the principal
eigenvectors of ``A^T A`` and ``A A^T`` respectively, where ``A`` is
the adjacency matrix.

Usage in the linker: the internal link graph is directed (source
post → target post). HITS gives us, *per node*, a quality measure
that complements PageRank — PageRank rewards popularity, HITS
rewards topical authority. Pair them via RRF for a more robust
ranking.

The helper wraps ``networkx.hits`` (already a project dep) so we
don't hand-roll power iteration. Output is a frozen dataclass so
callers can serialise the scores without fiddling with tuples.

**No DB access.** Callers load the graph (via
:mod:`apps.pipeline.services.weighted_pagerank`'s loader, for
example) and hand a ``networkx.DiGraph`` in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

import networkx as nx


#: networkx default; Kleinberg's paper shows convergence within a few
#: dozen iterations for typical web subgraphs. Raising this costs
#: linear time; lowering it risks non-convergence on dense graphs.
DEFAULT_MAX_ITERATIONS: int = 100

#: Convergence tolerance — sum of absolute changes across all nodes.
DEFAULT_TOLERANCE: float = 1e-8


@dataclass(frozen=True)
class HitsScores:
    """Per-node HITS authority and hub scores.

    Both dictionaries share the same key set (all graph nodes) and
    sum to 1.0 after networkx's built-in normalisation, so callers
    can treat the values as probabilities if they want.
    """

    authority: dict[Hashable, float]
    hub: dict[Hashable, float]


def compute(
    graph: nx.DiGraph,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
    normalized: bool = True,
) -> HitsScores:
    """Return :class:`HitsScores` for *graph*.

    Parameters
    ----------
    graph
        Directed graph. Undirected graphs are rejected — HITS's
        distinction between authorities and hubs only makes sense on
        a directed edge set.
    max_iterations, tolerance
        Forwarded to ``networkx.hits``. See the module docstring for
        defaults.
    normalized
        If ``True`` (the default) the score vectors sum to 1.0 —
        matches networkx's default and makes the output comparable
        across graphs of different sizes.

    Empty graphs return empty dicts (not an error — the caller may
    ingest an empty subgraph from a freshly-seeded system).
    """
    if not graph.is_directed():
        raise ValueError("HITS requires a directed graph")
    if graph.number_of_nodes() == 0:
        return HitsScores(authority={}, hub={})

    hub, authority = nx.hits(
        graph,
        max_iter=max_iterations,
        tol=tolerance,
        normalized=normalized,
    )
    return HitsScores(authority=dict(authority), hub=dict(hub))


def top_authorities(
    scores: HitsScores,
    k: int,
) -> list[tuple[Hashable, float]]:
    """Return the top-*k* authorities as ``(node, score)`` pairs.

    Ties broken by stringified node key for deterministic output.
    """
    if k < 0:
        raise ValueError("k must be >= 0")
    items = list(scores.authority.items())
    items.sort(key=lambda pair: (-pair[1], str(pair[0])))
    return items[:k]


def top_hubs(
    scores: HitsScores,
    k: int,
) -> list[tuple[Hashable, float]]:
    """Return the top-*k* hubs as ``(node, score)`` pairs."""
    if k < 0:
        raise ValueError("k must be >= 0")
    items = list(scores.hub.items())
    items.sort(key=lambda pair: (-pair[1], str(pair[0])))
    return items[:k]
