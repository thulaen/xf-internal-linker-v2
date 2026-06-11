import networkit as nk
from apps.graph.services.signals.group_seeds import compute_group_closeness_seeds

def test_compute_group_closeness_seeds():
    # *Given* a disconnected graph with two islands
    G = nk.Graph(5, directed=False)
    # Island 1: 0-1-2
    G.addEdge(0, 1)
    G.addEdge(1, 2)
    
    # Island 2: 3-4
    G.addEdge(3, 4)
    
    # *When* group-closeness runs with k=1
    # per-component seeds: it will pick 1 seed from island 1, and 1 seed from island 2.
    seeds, ranks = compute_group_closeness_seeds(G, 1)
    
    # *Then* we get seeds from both components
    # Island 1 center is 1. Island 2 center can be 3 or 4.
    assert 1 in seeds
    assert (3 in seeds) or (4 in seeds)
    
    # Ranks should reflect component size descending
    assert ranks[1] == 0  # Node 1 is from the larger component
    assert ranks[seeds[1]] == 1

def test_group_closeness_empty():
    G = nk.Graph(0, directed=False)
    seeds, ranks = compute_group_closeness_seeds(G, 1)
    assert seeds == []
    assert ranks == {}
