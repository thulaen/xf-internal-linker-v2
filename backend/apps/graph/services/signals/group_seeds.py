import networkit as nk

def compute_group_closeness_seeds(graph: nk.Graph, k: int) -> tuple[list[int], dict[int, int]]:
    """
    Computes group closeness seeds.
    Returns:
      - ranked_seeds: list of node indices (the most central nodes).
      - seed_ranks: dict mapping node_idx to rank (0-indexed, where 0 is best).
    Handles disconnected graphs by finding per-component seeds.
    """
    ranked_seeds = []
    seed_ranks = {}
    
    if graph.numberOfNodes() == 0:
        return ranked_seeds, seed_ranks

    if graph.isDirected():
        wcc = nk.components.WeaklyConnectedComponents(graph)
    else:
        wcc = nk.components.ConnectedComponents(graph)
    wcc.run()
    
    partitions = wcc.getPartition()
    components = partitions.subsetSizes()
    
    # Process each component
    # To keep seeds ranked, we might want to collect all seeds and then rank them by their component size or something,
    # or just yield them. We'll assign ranks as we find them.
    
    all_seeds = []
    for comp_id, size in enumerate(components):
        if size == 0:
            continue
        
        # Get nodes in this component
        nodes_in_comp = partitions.getMembers(comp_id)
        
        # If component is small, just take the first min(k, size) nodes
        comp_k = min(k, size)
        if comp_k <= 0:
            continue
            
        # Extract subgraph
        # networkit.graphtools.subgraphFromNodes is available in newer networkit
        # but we can also use GroupCloseness directly if it's connected?
        # Actually GroupCloseness on a subgraph is better because distances are only within component.
        subgraph = nk.graphtools.subgraphFromNodes(graph, nodes_in_comp)
        
        # Map subgraph nodes back to original graph nodes
        # subgraph nodes are contiguous 0..size-1, we need to map them back.
        # But wait, subgraphFromNodes in networkit creates a subgraph where node IDs are preserved if compact=False, 
        # but by default it might compact.
        # Let's check how to do this safely.
        
        # A simpler way: we can run GroupCloseness on the whole graph, but does it work per-component?
        # The edge case says "group-closeness on a disconnected graph (per-component seeds)".
        # Let's just create a new compact graph for the component.
        
        # GroupCloseness requires an undirected graph.
        comp_graph = nk.Graph(size, directed=False)
        orig_to_comp = {}
        comp_to_orig = {}
        for i, u in enumerate(nodes_in_comp):
            orig_to_comp[u] = i
            comp_to_orig[i] = u
            
        for u in nodes_in_comp:
            for v in graph.iterNeighbors(u):
                if v in orig_to_comp: # Should always be true for components
                    comp_graph.addEdge(orig_to_comp[u], orig_to_comp[v])
                    
        # Now run GroupCloseness
        gc = nk.centrality.GroupCloseness(comp_graph, comp_k)
        gc.run()
        comp_seeds = gc.groupMaxCloseness()
        
        # Map back to original IDs
        for s in comp_seeds:
            orig_s = comp_to_orig[s]
            all_seeds.append((orig_s, size)) # Tuple of (node, component_size) for sorting
            
    # Sort seeds by component size descending, then by node id for determinism
    all_seeds.sort(key=lambda x: (-x[1], x[0]))
    
    for rank, (node, _) in enumerate(all_seeds):
        ranked_seeds.append(node)
        seed_ranks[node] = rank
        
    return ranked_seeds, seed_ranks
