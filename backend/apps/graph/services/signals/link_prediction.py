import networkit as nk

def compute_link_prediction(graph: nk.Graph, id_to_idx: dict[int, int], idx_to_id: dict[int, int], top_k: int) -> list[dict]:
    """
    Computes structural link prediction candidates using Adamic-Adar, Common Neighbors, and Jaccard.
    Returns the top-K candidates per source.
    """
    aa_index = nk.linkprediction.AdamicAdarIndex(graph)
    cn_index = nk.linkprediction.CommonNeighborsIndex(graph)
    jc_index = nk.linkprediction.JaccardIndex(graph)
    
    candidates = []
    
    for u in graph.iterNodes():
        u_id = idx_to_id[u]
        
        # Find 2-hop neighbors (candidates)
        neighbors = set()
        for v in graph.iterNeighbors(u):
            neighbors.add(v)
            
        candidates_u = set()
        for v in neighbors:
            for w in graph.iterNeighbors(v):
                if w != u and w not in neighbors:
                    candidates_u.add(w)
                    
        scored = []
        for w in candidates_u:
            aa = float(aa_index.run(u, w))
            if aa > 0.0:
                cn = float(cn_index.run(u, w))
                jc = float(jc_index.run(u, w))
                scored.append({
                    "from_id": u_id,
                    "to_id": idx_to_id[w],
                    "adamic_adar": aa,
                    "common_neighbors": cn,
                    "jaccard": jc,
                    "_tie": idx_to_id[w]
                })
                
        # Sort by Adamic-Adar DESC, then by target ID ASC for determinism
        scored.sort(key=lambda x: (-x["adamic_adar"], x["_tie"]))
        
        top_scored = scored[:top_k]
        for s in top_scored:
            del s["_tie"]
            candidates.append(s)
            
    return candidates
