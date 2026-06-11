import networkit as nk
from typing import Dict, List, Any

def compute_communities(graph: nk.Graph, seed: int = 42) -> Dict[int, int]:
    """
    Computes community partitions using the Louvain algorithm.
    Returns mapping from node_idx to community_id.
    """
    if graph.numberOfNodes() == 0:
        return {}
    
    # Ensure determinism across runs
    nk.setSeed(seed, False)
    
    # Parallel Louvain Method
    plm = nk.community.PLM(graph)
    plm.run()
    
    partition = plm.getPartition()
    
    communities = {}
    for node in graph.iterNodes():
        communities[node] = partition.subsetOf(node)
        
    return communities

def flag_candidate_community_and_bridge(
    candidates: List[Dict[str, Any]],
    communities: Dict[int, int],
    id_to_idx: Dict[int, int]
) -> List[Dict[str, Any]]:
    """
    Updates the list of link candidate dicts with:
    - same_community: True if from_item and to_item share a Louvain community
    - is_bridge: True if they do not share a community (bridges between topics).
    """
    for candidate in candidates:
        from_idx = id_to_idx.get(candidate["from_id"])
        to_idx = id_to_idx.get(candidate["to_id"])
        
        if from_idx is None or to_idx is None:
            candidate["same_community"] = False
            candidate["is_bridge"] = False
            continue
            
        c_from = communities.get(from_idx)
        c_to = communities.get(to_idx)
        
        if c_from is None or c_to is None:
            candidate["same_community"] = False
            candidate["is_bridge"] = False
            continue
            
        same = (c_from == c_to)
        candidate["same_community"] = same
        candidate["is_bridge"] = not same
        
    return candidates
