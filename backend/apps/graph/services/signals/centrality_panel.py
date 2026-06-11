import networkit as nk
from apps.pipeline.services.hardware_profile import polars_thread_count

def compute_centrality_panel(graph: nk.Graph) -> dict[int, dict]:
    """
    Computes eigenvector, Katz, and closeness centralities.
    Returns:
        dict[node_idx, {
            "eigenvector": float,
            "katz": float,
            "closeness": float
        }]
    """
    nk.setNumberOfThreads(polars_thread_count())
    
    if graph.numberOfNodes() < 5:
        # Avoid hanging power iteration on tiny graphs
        result = {}
        for u in graph.iterNodes():
            result[u] = {
                "eigenvector": 0.0,
                "katz": 0.0,
                "closeness": 0.0,
            }
        return result

    # 1. Eigenvector
    ev = nk.centrality.EigenvectorCentrality(graph)
    try:
        ev.run()
        ev_scores = ev.scores()
    except Exception:
        ev_scores = [0.0] * graph.upperNodeIdBound()

    # 2. Katz (with non-convergence guard)
    katz = nk.centrality.KatzCentrality(graph)
    try:
        katz.run()
        katz_scores = katz.scores()
    except Exception:
        katz_scores = [0.0] * graph.upperNodeIdBound()

    # 3. Closeness
    # ClosenessVariant.GENERALIZED works for non-connected graphs
    # ApproxCloseness requires connected graphs, so we'll use exact Closeness 
    # with the generalized variant if graph is small, otherwise try ApproxCloseness
    # or fallback to generalized exact.
    # We will use ApproxCloseness if node count > 10000, but since ApproxCloseness
    # expects a connected graph, we might get errors. Let's wrap in try-except.
    if graph.numberOfNodes() > 10000:
        cl = nk.centrality.ApproxCloseness(graph, 100, normalized=True)
        try:
            cl.run()
            cl_scores = cl.scores()
        except Exception:
            # Fallback to exact generalized closeness if ApproxCloseness fails (e.g. disconnected)
            cl_exact = nk.centrality.Closeness(graph, True, nk.centrality.ClosenessVariant.GENERALIZED)
            try:
                cl_exact.run()
                cl_scores = cl_exact.scores()
            except Exception:
                cl_scores = [0.0] * graph.upperNodeIdBound()
    else:
        cl = nk.centrality.Closeness(graph, True, nk.centrality.ClosenessVariant.GENERALIZED)
        try:
            cl.run()
            cl_scores = cl.scores()
        except Exception:
            cl_scores = [0.0] * graph.upperNodeIdBound()

    result = {}
    for u in graph.iterNodes():
        result[u] = {
            "eigenvector": float(ev_scores[u]),
            "katz": float(katz_scores[u]),
            "closeness": float(cl_scores[u]),
        }
    return result
