import pytest
import networkit as nk

from apps.graph.services.signals.community import compute_communities, flag_candidate_community_and_bridge

pytestmark = pytest.mark.django_db

def test_compute_communities():
    """
    Given two dense clusters joined by one bridge node,
    When Louvain runs,
    Then the two clusters get distinct community ids.
    """
    # Create graph with two triangles connected by a bridge
    # Cluster 1: 0, 1, 2
    # Cluster 2: 3, 4, 5
    # Bridge: 6 (connected to 2 and 3)
    graph = nk.Graph(7, directed=False)
    graph.addEdge(0, 1)
    graph.addEdge(1, 2)
    graph.addEdge(2, 0)
    
    graph.addEdge(3, 4)
    graph.addEdge(4, 5)
    graph.addEdge(5, 3)
    
    graph.addEdge(2, 6)
    graph.addEdge(6, 3)
    
    communities = compute_communities(graph)
    
    assert communities[0] == communities[1] == communities[2]
    assert communities[3] == communities[4] == communities[5]
    assert communities[0] != communities[3]

def test_flag_candidate_community_and_bridge():
    """
    Given a candidate pair in the same community,
    When flagged,
    Then same_community=True.
    """
    communities = {0: 1, 1: 1, 2: 2, 3: 2}
    
    idx_to_id = {0: 100, 1: 101, 2: 102, 3: 103}
    id_to_idx = {v: k for k, v in idx_to_id.items()}
    
    candidates = [
        {"from_id": 100, "to_id": 101}, # same community -> is_bridge=False
        {"from_id": 100, "to_id": 102}, # diff community -> is_bridge=True
    ]
    
    flagged = flag_candidate_community_and_bridge(candidates, communities, id_to_idx)
    
    assert flagged[0]["same_community"] is True
    assert flagged[0]["is_bridge"] is False
    
    assert flagged[1]["same_community"] is False
    assert flagged[1]["is_bridge"] is True

def test_fully_connected_graph():
    """
    Given a fully-connected graph (one community);
    When Louvain runs,
    Then all nodes get the same community ID.
    """
    graph = nk.Graph(4, directed=False)
    for i in range(4):
        for j in range(i + 1, 4):
            graph.addEdge(i, j)
            
    communities = compute_communities(graph)
    assert len(set(communities.values())) == 1

def test_disconnected_graph():
    """
    Given a disconnected graph (per-island communities);
    When Louvain runs,
    Then islands get different community IDs.
    """
    graph = nk.Graph(4, directed=False)
    graph.addEdge(0, 1)
    graph.addEdge(2, 3)
    
    communities = compute_communities(graph)
    assert communities[0] == communities[1]
    assert communities[2] == communities[3]
    assert communities[0] != communities[2]
