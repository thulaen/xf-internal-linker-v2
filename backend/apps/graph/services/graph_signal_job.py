from __future__ import annotations

import concurrent.futures
from collections import Counter
import hashlib
import json
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink, GraphSignalRun, NodeGraphSignal, LinkPredictionCandidate
from apps.graph.services.networkit_graph import build_nk_graph
from apps.pipeline.services import disk_pressure

from apps.graph.services.signals import (
    betweenness,
    centrality_panel,
    clustering,
    community,
    core_components,
    group_seeds,
    link_prediction,
    reach,
    structural_embedding,
)

import networkit as nk

logger = logging.getLogger(__name__)


def load_active_edges() -> tuple[list[tuple[int, int]], list[int]]:
    """
    Load active edges from ExistingLink and all enabled ContentItems.
    Returns (edges, extra_nodes).
    """
    edges_qs = ExistingLink.objects.filter(
        from_content_item__is_deleted=False,
        to_content_item__is_deleted=False
    ).values_list("from_content_item_id", "to_content_item_id").distinct()
    
    edges = [(src, dst) for src, dst in edges_qs if src and dst]
    
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
    signal_version: str = "v1.0",
    dry_run: bool = False,
    icpc_min_community_size: int = 10,
) -> tuple[GraphSignalRun, Optional[tuple[nk.Graph, dict[int, int], list[int]]]]:
    """
    Orchestrates building the NetworKit graph and computing all signals.
    """
    params = {"icpc_min_community_size": int(icpc_min_community_size)}
    edges, extra_nodes = load_active_edges()
    current_hash = compute_graph_hash(edges)
    
    if not force:
        existing_run = GraphSignalRun.objects.filter(
            graph_hash=current_hash,
            signal_version=signal_version,
            params_json=params,
            status=GraphSignalRun.STATUS_CURRENT
        ).first()
        if existing_run:
            logger.info("Graph unchanged; returning existing run.")
            return existing_run, None

    # Enforce disk pressure limit before allocating DB models
    disk_pressure.require_free_disk(estimated_bytes=50 * 1024 * 1024)

    # Pre-create run as computing
    with transaction.atomic():
        run = GraphSignalRun.objects.create(
            graph_hash=current_hash,
            signal_version=signal_version,
            node_count=0,
            edge_count=0,
            status=GraphSignalRun.STATUS_COMPUTING,
            params_json=params,
        )
        
    nk_graph, id_to_idx, idx_to_id = build_nk_graph(edges, extra_nodes=extra_nodes)
    
    run.node_count = nk_graph.numberOfNodes()
    run.edge_count = nk_graph.numberOfEdges()
    run.save(update_fields=["node_count", "edge_count"])

    # Some algorithms (PLM, CoreDecomposition, LocalClusteringCoefficient) strictly require
    # an undirected graph. Passing a directed graph to them in C++ hangs the thread infinitely.
    nk_graph_undirected = nk.graphtools.toUndirected(nk_graph)

    # 1. Concurrent execution of cheap node signals.
    # Note: Using a ThreadPoolExecutor instead of a Celery group because passing the C++ nk_graph
    # across process boundaries requires pickling (impossible) or rebuilding the graph per worker
    # (which violates the ADR: "built exactly once per run"). NetworKit releases the GIL.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        fut_comm = executor.submit(community.compute_communities, nk_graph_undirected)
        fut_betw = executor.submit(betweenness.compute_betweenness, nk_graph)
        fut_cent = executor.submit(centrality_panel.compute_centrality_panel, nk_graph)
        fut_core = executor.submit(core_components.compute_core_numbers, nk_graph_undirected)
        fut_comp = executor.submit(core_components.compute_components, nk_graph)
        fut_clus = executor.submit(clustering.compute_local_clustering, nk_graph_undirected)
        fut_grp = executor.submit(group_seeds.compute_group_closeness_seeds, nk_graph, 100)
        
        community_ids = fut_comm.result()
        betweenness_scores = fut_betw.result()
        centrality_dict = fut_cent.result()
        core_nums = fut_core.result()
        components = fut_comp.result()
        clustering_dict = fut_clus.result()
        group_seeds_list, _ = fut_grp.result()

    # Reach requires DB lookup for hub seeds
    hub_ids = set(ContentItem.objects.order_by('-march_2026_pagerank_score').values_list('id', flat=True)[:100])
    hub_seeds_idx = [id_to_idx[db_id] for db_id in hub_ids if db_id in id_to_idx]
    reach_scores = reach.compute_click_depth(nk_graph, hub_seeds_idx)
    
    group_seed_rank_dict = {idx: rank for rank, idx in enumerate(group_seeds_list)}
    icpc_local, icpc_global = _compute_icpc_degrees(
        edges=edges,
        id_to_idx=id_to_idx,
        community_ids=community_ids,
        min_community_size=icpc_min_community_size,
    )
    
    # 2. Heavy signals
    embeddings = structural_embedding.compute_structural_embeddings(nk_graph)
    link_candidates = link_prediction.compute_link_prediction(nk_graph_undirected, id_to_idx, idx_to_id, top_k=2000)
    # The id_to_idx mapping matches strings/ints internally via `.get()`, but we can pass string keys explicitly if needed.
    str_id_to_idx = {str(k): v for k, v in id_to_idx.items()}
    structural_embedding.populate_candidate_cosine(link_candidates, embeddings, str_id_to_idx)
    
    for cand in link_candidates:
        u_id = cand["from_id"]
        v_id = cand["to_id"]
        u_idx = id_to_idx.get(u_id)
        v_idx = id_to_idx.get(v_id)
        cand["same_community"] = False
        cand["is_bridge"] = False
        if u_idx is not None and v_idx is not None:
            comm_u = community_ids.get(u_idx)
            comm_v = community_ids.get(v_idx)
            if comm_u is not None and comm_v is not None:
                if comm_u == comm_v:
                    cand["same_community"] = True
                else:
                    cand["is_bridge"] = True

    # 3. Create NodeGraphSignals
    node_signals_to_create = []
    for db_id, idx in id_to_idx.items():
        cent = centrality_dict.get(idx, {})
        comp_info = components.get(idx, {})
        
        r_dict = reach_scores.get(idx, {})
        inbound_reachable = r_dict.get("inbound_reachable", False)
        is_orphan = r_dict.get("is_orphan", True)
        r_depth = r_dict.get("depth")

        node_signals_to_create.append(NodeGraphSignal(
            run=run,
            content_item_id=db_id,
            community_id=community_ids.get(idx),
            icpc_local_indegree=icpc_local.get(idx, 0),
            icpc_global_indegree=icpc_global.get(idx, 0),
            betweenness=betweenness_scores.get(idx),
            click_depth=r_depth if inbound_reachable else None,
            inbound_reachable=inbound_reachable,
            is_orphan=is_orphan,
            eigenvector=cent.get("eigenvector"),
            katz=cent.get("katz"),
            closeness=cent.get("closeness"),
            core_number=core_nums.get(idx),
            component_id=comp_info.get("component_id"),
            is_main_component=comp_info.get("is_main_component", False),
            local_clustering=clustering_dict.get(idx),
            group_seed_rank=group_seed_rank_dict.get(idx),
            node2vec_embedding=embeddings.get(idx)
        ))
        
    link_candidates_to_create = []
    for cand in link_candidates:
        link_candidates_to_create.append(LinkPredictionCandidate(
            run=run,
            from_item_id=cand["from_id"],
            to_item_id=cand["to_id"],
            adamic_adar=cand.get("adamic_adar"),
            common_neighbors=cand.get("common_neighbors"),
            jaccard=cand.get("jaccard"),
            same_community=cand.get("same_community", False),
            is_bridge=cand.get("is_bridge", False),
            embed_cosine=cand.get("embed_cosine")
        ))

    with transaction.atomic():
        # Bulk insert
        NodeGraphSignal.objects.bulk_create(node_signals_to_create, batch_size=5000)
        LinkPredictionCandidate.objects.bulk_create(link_candidates_to_create, batch_size=5000)
        
        # Flip to current
        run.status = GraphSignalRun.STATUS_CURRENT
        run.computed_at = timezone.now()
        run.save(update_fields=["status", "computed_at"])
        
        # Supersede old ones
        GraphSignalRun.objects.filter(
            status=GraphSignalRun.STATUS_CURRENT
        ).exclude(id=run.id).update(status=GraphSignalRun.STATUS_SUPERSEDED)
        
        # Prune older than 2 superseded
        superseded = GraphSignalRun.objects.filter(
            status=GraphSignalRun.STATUS_SUPERSEDED
        ).order_by('-computed_at')
        
        if superseded.count() > 2:
            runs_to_delete = superseded[2:].values_list('id', flat=True)
            # Cascade deletes the related NodeGraphSignal and LinkPredictionCandidate rows
            GraphSignalRun.objects.filter(id__in=runs_to_delete).delete()

        if dry_run:
            logger.info("Dry run: rolling back transaction")
            transaction.set_rollback(True)

    if dry_run:
        run.delete()

    return run, (nk_graph, id_to_idx, idx_to_id)


def _compute_icpc_degrees(
    *,
    edges: list[tuple[int, int]],
    id_to_idx: dict[int, int],
    community_ids: dict[int, int],
    min_community_size: int,
) -> tuple[dict[int, int], dict[int, int]]:
    """Compute ICPC local and global in-degree per graph index."""
    community_sizes = Counter(community_ids.values())
    local: Counter[int] = Counter()
    global_: Counter[int] = Counter()
    for source_id, destination_id in set(edges):
        source_idx = id_to_idx.get(source_id)
        destination_idx = id_to_idx.get(destination_id)
        if source_idx is None or destination_idx is None:
            continue
        global_[destination_idx] += 1
        source_community = community_ids.get(source_idx)
        destination_community = community_ids.get(destination_idx)
        if (
            source_community is not None
            and source_community == destination_community
            and community_sizes[destination_community] >= min_community_size
        ):
            local[destination_idx] += 1
    return dict(local), dict(global_)
