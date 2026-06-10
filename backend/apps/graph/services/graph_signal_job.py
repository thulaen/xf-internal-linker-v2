from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from django.db import transaction

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink, GraphSignalRun
from apps.graph.services.networkit_graph import build_nk_graph
import networkit as nk

logger = logging.getLogger(__name__)

def load_active_edges() -> tuple[list[tuple[int, int]], list[int]]:
    """
    Load active edges from ExistingLink and all enabled ContentItems.
    Returns (edges, extra_nodes).
    """
    # Active edges (source and target items must not be deleted)
    edges_qs = ExistingLink.objects.filter(
        from_content_item__is_deleted=False,
        to_content_item__is_deleted=False
    ).values_list("from_content_item_id", "to_content_item_id").distinct()
    
    edges = [(src, dst) for src, dst in edges_qs if src and dst]
    
    # All active content items
    extra_nodes = list(
        ContentItem.objects.filter(is_deleted=False).values_list("id", flat=True)
    )
    
    return edges, extra_nodes

def compute_graph_hash(edges: list[tuple[int, int]]) -> str:
    """Compute a SHA-256 hash of the sorted active edge list."""
    sorted_edges = sorted(set(edges))
    encoded = json.dumps(sorted_edges).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def run_signals(
    force: bool = False,
    signal_version: str = "v1.0"
) -> tuple[GraphSignalRun, Optional[tuple[nk.Graph, dict[int, int], list[int]]]]:
    """
    Orchestrates building the NetworKit graph.
    If the graph hasn't changed (matched by graph_hash and signal_version) and force=False,
    it skips building and returns the existing run.
    """
    edges, extra_nodes = load_active_edges()
    current_hash = compute_graph_hash(edges)
    
    if not force:
        existing_run = GraphSignalRun.objects.filter(
            graph_hash=current_hash,
            signal_version=signal_version,
            status=GraphSignalRun.STATUS_CURRENT
        ).first()
        if existing_run:
            logger.info("unchanged")
            return existing_run, None

    with transaction.atomic():
        run = GraphSignalRun.objects.create(
            graph_hash=current_hash,
            signal_version=signal_version,
            node_count=0,
            edge_count=0,
            status=GraphSignalRun.STATUS_COMPUTING
        )
        
    nk_graph, id_to_idx, idx_to_id = build_nk_graph(edges, extra_nodes=extra_nodes)
    
    run.node_count = nk_graph.numberOfNodes()
    run.edge_count = nk_graph.numberOfEdges()
    run.save(update_fields=["node_count", "edge_count"])
    
    return run, (nk_graph, id_to_idx, idx_to_id)
