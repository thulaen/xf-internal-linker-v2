import networkit as nk
from typing import Dict

from apps.pipeline.services.hardware_profile import detect_profile, polars_thread_count

def _get_betweenness_estimator_threshold() -> int:
    """Returns the node count threshold above which we use the Betweenness Estimator."""
    profile = detect_profile()
    return {"low": 1000, "medium": 5000, "high": 10000, "workstation": 20000}.get(profile.tier, 5000)

def compute_betweenness(graph: nk.Graph, estimator_threshold: int | None = None) -> Dict[int, float]:
    """
    Computes betweenness centrality for all nodes in the graph.
    Uses exact algorithm for small graphs, estimator for large graphs.
    Returns mapping from node_idx to betweenness score.
    """
    node_count = graph.numberOfNodes()
    if node_count == 0:
        return {}
        
    if estimator_threshold is None:
        estimator_threshold = _get_betweenness_estimator_threshold()
        
    # Cap threads to leave Celery headroom
    nk.setNumberOfThreads(polars_thread_count())
    
    if node_count > estimator_threshold:
        # We need at least a few samples, up to 256 for a reasonable estimate
        samples = min(256, max(1, int(node_count * 0.1)))
        bc = nk.centrality.EstimateBetweenness(graph, samples, normalized=False, parallel=True)
    else:
        bc = nk.centrality.Betweenness(graph, normalized=False)
        
    bc.run()
    
    scores = {}
    scores_list = bc.scores()
    
    for node in graph.iterNodes():
        if node < len(scores_list):
            scores[node] = scores_list[node]
            
    return scores
