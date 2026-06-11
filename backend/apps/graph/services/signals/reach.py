import networkit as nk
import math

from apps.pipeline.services.hardware_profile import polars_thread_count

UNREACHABLE_DEPTH = float("inf")

def compute_click_depth(graph: nk.Graph, hub_seeds: list[int]) -> dict[int, dict]:
    """
    Computes click-depth (shortest paths) from the given hub seeds.
    Identifies orphan nodes (in-degree 0).
    
    Returns:
        dict[node_idx, {
            "depth": int | float,
            "inbound_reachable": bool,
            "is_orphan": bool
        }]
    """
    nk.setNumberOfThreads(polars_thread_count())
    min_depths = {u: UNREACHABLE_DEPTH for u in graph.iterNodes()}
    
    for seed in hub_seeds:
        if not graph.hasNode(seed):
            continue
        
        bfs = nk.distance.BFS(graph, seed)
        bfs.run()
        distances = bfs.getDistances()
        
        for u in graph.iterNodes():
            d = distances[u]
            if d < 1e300 and d < min_depths[u]:
                min_depths[u] = float(d)
                
    result = {}
    for u in graph.iterNodes():
        depth = min_depths[u]
        is_reachable = depth != UNREACHABLE_DEPTH and not math.isinf(depth)
        
        # In directed graphs, inDegree counts inbound edges
        is_orphan = graph.degreeIn(u) == 0 if graph.isDirected() else graph.degree(u) == 0
        
        result[u] = {
            "depth": int(depth) if is_reachable else UNREACHABLE_DEPTH,
            "inbound_reachable": is_reachable,
            "is_orphan": is_orphan,
        }
        
    return result
