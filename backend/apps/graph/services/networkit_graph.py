"""Build a NetworKit graph from the internal link graph (graph.ExistingLink edges).

Phase NK — docs/specs/fr-networkit-graph-signals.md. These are **pure** helpers with no
Django/DB imports, so the graph construction is unit-testable in isolation. The DB-facing
layer (reading ExistingLink, writing signal rows on a schedule) lives in graph_signal_job.py.

Nodes are ContentItem ids; edges are directed (from_content_item -> to_content_item).
NetworKit needs dense 0..n-1 node indices, so we map the (sparse) ContentItem ids to a
dense index and keep the inverse to translate results back.

Source: Staudt, Sazonovs & Meyerhenke 2016 (doi:10.1017/nws.2016.20).
"""
from __future__ import annotations

import networkit as nk


def build_nk_graph(
    edges: list[tuple[int, int]],
    extra_nodes: list[int] | None = None,
) -> tuple[nk.Graph, dict[int, int], list[int]]:
    """Build a directed NetworKit graph from (from_id, to_id) ContentItem edges.

    Returns ``(graph, id_to_idx, idx_to_id)``:
      * ``graph``     — a directed ``networkit.Graph``.
      * ``id_to_idx`` — maps a ContentItem id to its dense NetworKit node index.
      * ``idx_to_id`` — the inverse list (node index -> ContentItem id).

    Self-loops are dropped (a page linking to itself is meaningless for these signals)
    and duplicate edges are collapsed (NetworKit is a simple graph). ``extra_nodes``
    includes isolated pages that have no links yet, so orphan/centrality signals see them.
    """
    node_ids: set[int] = set(extra_nodes or [])
    for src, dst in edges:
        node_ids.add(src)
        node_ids.add(dst)

    idx_to_id: list[int] = sorted(node_ids)
    id_to_idx: dict[int, int] = {node_id: idx for idx, node_id in enumerate(idx_to_id)}

    graph = nk.Graph(len(idx_to_id), directed=True)
    seen: set[tuple[int, int]] = set()
    for src, dst in edges:
        if src == dst:
            continue  # skip self-loops
        edge = (id_to_idx[src], id_to_idx[dst])
        if edge in seen:
            continue  # collapse duplicate edges (simple graph)
        seen.add(edge)
        graph.addEdge(edge[0], edge[1])
    return graph, id_to_idx, idx_to_id
