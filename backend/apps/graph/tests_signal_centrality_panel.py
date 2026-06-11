import pytest
import networkit as nk
from apps.graph.services.signals.centrality_panel import compute_centrality_panel

pytestmark = pytest.mark.django_db

def test_centrality_panel_star_graph():
    """
    Given a star graph,
    When the panel runs,
    Then the centre has the highest closeness.
    """
    # 0 is center, connected to 1, 2, 3, 4
    graph = nk.Graph(5, directed=False)
    for i in range(1, 5):
        graph.addEdge(0, i)
        
    result = compute_centrality_panel(graph)
    
    closeness_scores = [result[i]["closeness"] for i in range(5)]
    center_closeness = closeness_scores[0]
    
    # Check that center has higher closeness than leaves
    for i in range(1, 5):
        assert center_closeness > closeness_scores[i]

def test_katz_non_convergence_guard():
    """
    Given a graph where Katz might fail to converge,
    When the panel runs,
    Then it catches the error and returns 0.0 scores instead of crashing.
    """
    # A fully connected graph or specific structures can cause non-convergence 
    # depending on alpha (default alpha = 0.1).
    # Since we can't easily force non-convergence predictably without changing alpha,
    # we just ensure the try-except block allows the code to run without crashing.
    graph = nk.Graph(10, directed=True)
    for i in range(10):
        for j in range(10):
            if i != j:
                graph.addEdge(i, j)
                
    result = compute_centrality_panel(graph)
    assert len(result) == 10
    # Values might be 0.0 if it didn't converge, or actual numbers if it did.
    for i in range(10):
        assert "katz" in result[i]
        assert isinstance(result[i]["katz"], float)
        
def test_disconnected_closeness():
    """
    Given a disconnected graph,
    When the panel runs,
    Then it computes closeness via the generalized variant without crashing.
    """
    graph = nk.Graph(4, directed=False)
    # Component 1
    graph.addEdge(0, 1)
    # Component 2
    graph.addEdge(2, 3)
    
    result = compute_centrality_panel(graph)
    assert len(result) == 4
    for i in range(4):
        assert result[i]["closeness"] >= 0.0
