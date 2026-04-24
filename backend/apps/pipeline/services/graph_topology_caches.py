"""Precompute builders for FR-099 through FR-105 graph-topology signals.

Built once per pipeline run in pipeline_data.py from the shared
`existing_links` edge list. Consumed per-candidate in the ranker
signal-module `evaluate_*` functions.

- FR-099 DARB — reuses existing_outgoing_counts (no new cache).
- FR-100 KMIG — builds KatzCache (adjacency + A² sparse matrices).
- FR-101 TAPB — builds ArticulationPointCache (AP set via networkx).
- FR-102 KCIB — builds KCoreCache (core_number via networkx).
- FR-103 BERP — builds BridgeEdgeCache (BCC labels via networkx).
- FR-104 HGTE — builds HostSiloDistributionCache from link + silo data.
- FR-105 RSQVA — builds QueryTFIDFCache from ContentItem vectors.

All builders are defensive: they return empty/cold-start caches if the
graph is too small (below BLC §6.4 minimum-data floors). Signal modules
handle those with neutral fallback.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable, Mapping, TypeAlias

import numpy as np

from .articulation_point_boost import ArticulationPointCache
from .bridge_edge_redundancy import BridgeEdgeCache
from .host_topic_entropy import HostSiloDistributionCache
from .katz_marginal_info import KatzCache, build_katz_cache_from_edges
from .kcore_integration import KCoreCache
from .search_query_alignment import QueryTFIDFCache

logger = logging.getLogger(__name__)

ContentKey: TypeAlias = tuple[int, str]


def _build_node_index(
    content_keys: Iterable[ContentKey],
) -> dict[ContentKey, int]:
    """Map every ContentKey to a stable integer index for numpy/scipy use."""
    return {key: idx for idx, key in enumerate(content_keys)}


def build_katz_cache(
    content_keys: Iterable[ContentKey],
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
) -> KatzCache:
    """FR-100 KMIG precompute.

    Builds the adjacency CSR and its square (2-hop path counts) over the
    directed link graph.
    """
    node_to_index = _build_node_index(content_keys)
    edge_list: list[tuple[int, int]] = []
    for from_key, to_key in existing_links:
        from_idx = node_to_index.get(from_key)
        to_idx = node_to_index.get(to_key)
        if from_idx is None or to_idx is None:
            continue
        edge_list.append((from_idx, to_idx))
    return build_katz_cache_from_edges(node_to_index, edge_list)


def _build_undirected_networkx_graph(
    content_keys: Iterable[ContentKey],
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
):
    """Return a networkx.Graph with nodes = content keys and undirected edges.

    Used for TAPB (articulation points), KCIB (k-core), and BERP
    (biconnected components) which all operate on undirected graphs.
    """
    # Lazy import networkx — heavy dependency, only needed when these signals run.
    import networkx as nx

    g = nx.Graph()
    for key in content_keys:
        g.add_node(key)
    for from_key, to_key in existing_links:
        if from_key == to_key:
            continue  # Skip self-loops — they don't affect AP/KC/BCC analysis
        g.add_edge(from_key, to_key)
    return g


def build_articulation_point_cache(
    content_keys: Iterable[ContentKey],
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
) -> ArticulationPointCache:
    """FR-101 TAPB precompute. O(V+E) via networkx Tarjan implementation."""
    import networkx as nx

    g = _build_undirected_networkx_graph(content_keys, existing_links)
    try:
        ap_set: frozenset = frozenset(nx.articulation_points(g))
    except Exception as exc:
        logger.warning("TAPB: networkx.articulation_points failed: %s", exc)
        ap_set = frozenset()
    return ArticulationPointCache(
        articulation_point_set=ap_set,
        total_graph_nodes=g.number_of_nodes(),
        articulation_point_count=len(ap_set),
    )


def build_kcore_cache(
    content_keys: Iterable[ContentKey],
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
) -> KCoreCache:
    """FR-102 KCIB precompute. Uses Batagelj-Zaversnik O(m) via networkx."""
    import networkx as nx

    g = _build_undirected_networkx_graph(content_keys, existing_links)
    # networkx.core_number requires removing self-loops first (our
    # _build_undirected_networkx_graph already skips self-loops but
    # double-guard).
    g.remove_edges_from(list(nx.selfloop_edges(g)))
    try:
        core_map: dict = dict(nx.core_number(g))
    except Exception as exc:
        logger.warning("KCIB: networkx.core_number failed: %s", exc)
        core_map = {}
    max_kcore = max(core_map.values()) if core_map else 0
    return KCoreCache(
        kcore_number_map=core_map,
        max_kcore=int(max_kcore),
        total_graph_nodes=g.number_of_nodes(),
    )


def build_bridge_edge_cache(
    content_keys: Iterable[ContentKey],
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
) -> BridgeEdgeCache:
    """FR-103 BERP precompute. BCC labels via networkx Hopcroft-Tarjan."""
    import networkx as nx

    g = _build_undirected_networkx_graph(content_keys, existing_links)
    bcc_label_map: dict[ContentKey, int] = {}
    bcc_size_map: dict[int, int] = {}
    try:
        for label, component in enumerate(nx.biconnected_components(g)):
            size = len(component)
            bcc_size_map[label] = size
            for node in component:
                # A node can belong to multiple BCCs (articulation points do);
                # we take the largest-BCC membership as the node's primary label.
                existing = bcc_label_map.get(node)
                if existing is None or bcc_size_map.get(existing, 0) < size:
                    bcc_label_map[node] = label
    except Exception as exc:
        logger.warning("BERP: networkx.biconnected_components failed: %s", exc)
    return BridgeEdgeCache(
        bcc_label_map=bcc_label_map,
        bcc_size_map=bcc_size_map,
        total_graph_nodes=g.number_of_nodes(),
    )


def build_host_silo_distribution_cache(
    existing_links: Iterable[tuple[ContentKey, ContentKey]],
    dest_silo_by_key: Mapping[ContentKey, int | None],
    num_silos: int,
) -> HostSiloDistributionCache:
    """FR-104 HGTE precompute.

    Counts each host's outbound edges by the destination's silo. Destinations
    with NULL silo are skipped (the candidate pair at eval time returns
    'dest_no_silo' fallback for those).
    """
    host_silo_counts: dict[ContentKey, dict[int, int]] = defaultdict(dict)
    for from_key, to_key in existing_links:
        dest_silo = dest_silo_by_key.get(to_key)
        if dest_silo is None:
            continue
        host_silo_counts[from_key][dest_silo] = (
            host_silo_counts[from_key].get(dest_silo, 0) + 1
        )
    return HostSiloDistributionCache(
        host_silo_counts=dict(host_silo_counts),
        num_silos=max(1, num_silos),
    )


def build_query_tfidf_cache(
    page_vectors: Mapping[ContentKey, np.ndarray],
    page_query_counts: Mapping[ContentKey, int],
    gsc_days_available: int,
) -> QueryTFIDFCache:
    """FR-105 RSQVA precompute.

    Vectors are expected to be L2-normalized by the refresh task
    (analytics.tasks.refresh_gsc_query_tfidf — deferred to follow-up
    session). If that task hasn't run yet, page_vectors is empty and
    eval returns `vector_not_computed` fallback.
    """
    return QueryTFIDFCache(
        page_vectors=page_vectors,
        page_query_counts=page_query_counts,
        gsc_days_available=gsc_days_available,
    )
