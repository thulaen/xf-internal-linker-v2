import networkit as nk

def compute_core_numbers(graph: nk.Graph) -> dict[int, int]:
    """
    Computes k-core decomposition for each node.
    Returns a dictionary mapping node_idx to core_number.
    """
    core_dec = nk.centrality.CoreDecomposition(graph)
    core_dec.run()
    scores = core_dec.scores()
    
    result = {}
    for u in graph.iterNodes():
        result[u] = int(scores[u])
    return result

def compute_components(graph: nk.Graph) -> dict[int, dict]:
    """
    Computes WeaklyConnectedComponents for the graph.
    Returns a dictionary mapping node_idx to {"component_id": int, "is_main_component": bool}.
    """
    if graph.isDirected():
        wcc = nk.components.WeaklyConnectedComponents(graph)
    else:
        wcc = nk.components.ConnectedComponents(graph)
        
    wcc.run()
    
    # Identify the main component (the one with the largest number of nodes)
    comp_sizes = wcc.getPartition().subsetSizes()
    main_comp_id = -1
    max_size = -1
    for comp_id, size in enumerate(comp_sizes):
        if size > max_size:
            max_size = size
            main_comp_id = comp_id
            
    result = {}
    for u in graph.iterNodes():
        c_id = wcc.componentOfNode(u)
        result[u] = {
            "component_id": c_id,
            "is_main_component": c_id == main_comp_id
        }
    return result
