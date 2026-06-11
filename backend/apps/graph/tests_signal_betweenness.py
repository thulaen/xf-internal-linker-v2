import pytest
import networkit as nk

from apps.graph.services.signals.betweenness import compute_betweenness

pytestmark = pytest.mark.django_db

def test_compute_betweenness():
    """
    Given the same graph (two dense clusters joined by one bridge node),
    When betweenness runs,
    Then the bridge node has the highest score.
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
    
    # We pass a low threshold to test exact algorithm
    betweenness = compute_betweenness(graph, estimator_threshold=100)
    
    # Node 6 acts as a bridge between the two clusters, should have highest score
    max_score_node = max(betweenness, key=betweenness.get)
    assert max_score_node == 6
    
    # We pass a high threshold (0) to force the EstimateBetweenness code path
    betweenness_est = compute_betweenness(graph, estimator_threshold=0)
    
    # Even estimated, it returns the right number of nodes and scores >= 0
    assert len(betweenness_est) == 7
    assert all(score >= 0 for score in betweenness_est.values())

def test_compute_betweenness_estimator_threshold_boundary():
    """
    Given a graph at the estimator threshold boundary,
    When betweenness runs,
    Then the appropriate algorithm is chosen silently (smoke test).
    """
    graph = nk.Graph(5, directed=False)
    for i in range(4):
        graph.addEdge(i, i+1)
        
    exact = compute_betweenness(graph, estimator_threshold=6)
    est = compute_betweenness(graph, estimator_threshold=4)
    
    # Both should complete and return dicts
    assert isinstance(exact, dict)
    assert isinstance(est, dict)
    assert len(exact) == 5
    assert len(est) == 5
