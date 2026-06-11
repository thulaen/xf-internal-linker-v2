import networkit as nk

def compute_local_clustering(graph: nk.Graph) -> dict[int, float]:
    """
    Computes local clustering coefficient for each node.
    Returns a dictionary mapping node_idx to float score (0.0 to 1.0).
    """
    lcc = nk.centrality.LocalClusteringCoefficient(graph)
    lcc.run()
    scores = lcc.scores()
    
    result = {}
    for u in graph.iterNodes():
        result[u] = float(scores[u])
    return result
