import networkit as nk
from apps.graph.services.signals.clustering import compute_local_clustering

def test_compute_local_clustering():
    # *Given* A->B and A->C with no B<->C
    # For undirected graphs, local clustering coefficient of A should be 0.
    G = nk.Graph(3, directed=False)
    G.addEdge(0, 1) # A-B
    G.addEdge(0, 2) # A-C
    
    # *When* clustering runs
    clustering = compute_local_clustering(G)
    
    # *Then* A's neighborhood is flagged triangle-closeable (clustering is 0)
    assert clustering[0] == 0.0
    
    # If we add B-C, it becomes a triangle, so A's clustering is 1.0
    G.addEdge(1, 2)
    clustering2 = compute_local_clustering(G)
    assert clustering2[0] == 1.0

def test_compute_local_clustering_single_node():
    G = nk.Graph(1, directed=False)
    clustering = compute_local_clustering(G)
    assert clustering[0] == 0.0
