import pytest
import networkit as nk

from apps.graph.services.signals.link_prediction import compute_link_prediction

pytestmark = pytest.mark.django_db

def test_link_prediction_triad():
    """
    Given a triad where A->C and B->C exist but A<->B don't,
    When link prediction runs,
    Then (A,B) scores > 0 on common-neighbors and appears as a candidate.
    """
    # Create graph with 3 nodes: 0 (A), 1 (B), 2 (C)
    # A->C, B->C
    graph = nk.Graph(3, directed=False)
    graph.addEdge(0, 2)
    graph.addEdge(1, 2)

    id_to_idx = {100: 0, 101: 1, 102: 2}
    idx_to_id = {0: 100, 1: 101, 2: 102}

    candidates = compute_link_prediction(graph, id_to_idx, idx_to_id, top_k=5)

    # We expect A (100) -> B (101) to have common neighbors = 1 (Node C)
    # The return list should have dicts with {from_id, to_id, adamic_adar, common_neighbors, jaccard}
    ab_candidates = [c for c in candidates if c["from_id"] == 100 and c["to_id"] == 101]
    
    assert len(ab_candidates) == 1
    assert ab_candidates[0]["common_neighbors"] == 1.0
    assert ab_candidates[0]["adamic_adar"] > 0.0

def test_link_prediction_exclude_existing():
    """
    Given an existing edge,
    When prediction runs,
    Then it is excluded from candidates.
    """
    graph = nk.Graph(3, directed=False)
    graph.addEdge(0, 1)
    graph.addEdge(1, 2)

    id_to_idx = {10: 0, 11: 1, 12: 2}
    idx_to_id = {0: 10, 1: 11, 2: 12}

    candidates = compute_link_prediction(graph, id_to_idx, idx_to_id, top_k=5)

    # (10, 11) is an existing edge, shouldn't be a candidate
    existing_candidates = [c for c in candidates if c["from_id"] == 10 and c["to_id"] == 11]
    assert len(existing_candidates) == 0

def test_link_prediction_top_k():
    """
    Given >K candidates for a source,
    When persisted,
    Then exactly K survive, highest first.
    """
    # 1 source, connected to 5 hubs. Each hub connected to 1 target.
    # Total targets = 5.
    graph = nk.Graph(11, directed=False)
    
    # Node 0 is the source
    # Nodes 1..5 are hubs
    # Nodes 6..10 are targets
    for i in range(1, 6):
        graph.addEdge(0, i)
        graph.addEdge(i, i+5)
        
    id_to_idx = {i*10: i for i in range(11)}
    idx_to_id = {i: i*10 for i in range(11)}
    
    candidates = compute_link_prediction(graph, id_to_idx, idx_to_id, top_k=2)
    
    # Source is 0 (id 0)
    source_candidates = [c for c in candidates if c["from_id"] == 0]
    
    # Only top 2 should survive
    assert len(source_candidates) == 2
