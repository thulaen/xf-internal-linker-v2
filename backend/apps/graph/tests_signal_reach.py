import pytest
import networkit as nk
from apps.graph.services.signals.reach import compute_click_depth, UNREACHABLE_DEPTH

pytestmark = pytest.mark.django_db

def test_click_depth_chain():
    """
    Given a hub and a chain hub->A->B,
    When click-depth runs,
    Then A=1, B=2.
    """
    # Nodes: 0 (hub), 1 (A), 2 (B)
    graph = nk.Graph(3, directed=True)
    graph.addEdge(0, 1)
    graph.addEdge(1, 2)
    
    hub_seeds = [0]
    result = compute_click_depth(graph, hub_seeds)
    
    assert result[0]["depth"] == 0
    assert result[1]["depth"] == 1
    assert result[2]["depth"] == 2
    
    assert result[0]["inbound_reachable"] is True
    assert result[1]["inbound_reachable"] is True
    assert result[2]["inbound_reachable"] is True

def test_reach_orphan():
    """
    Given a node with no inbound links,
    When reach runs,
    Then is_orphan=True and depth=UNREACHABLE_DEPTH.
    """
    # 0 -> 1, 2 is isolated
    graph = nk.Graph(3, directed=True)
    graph.addEdge(0, 1)
    
    result = compute_click_depth(graph, hub_seeds=[0])
    
    assert result[2]["is_orphan"] is True
    assert result[2]["inbound_reachable"] is False
    assert result[2]["depth"] == UNREACHABLE_DEPTH
    
    # 0 has out-degree 1, in-degree 0 (orphan)
    assert result[0]["is_orphan"] is True
    
    # 1 has in-degree 1 (not orphan)
    assert result[1]["is_orphan"] is False

def test_multiple_hubs():
    # 0 -> 1 -> 2
    # 3 -> 2
    graph = nk.Graph(4, directed=True)
    graph.addEdge(0, 1)
    graph.addEdge(1, 2)
    graph.addEdge(3, 2)
    
    result = compute_click_depth(graph, hub_seeds=[0, 3])
    
    assert result[0]["depth"] == 0
    assert result[3]["depth"] == 0
    assert result[1]["depth"] == 1
    # 2 is reachable from 3 in 1 step, from 0 in 2 steps. Min is 1.
    assert result[2]["depth"] == 1

def test_empty_hubs():
    """If no hub seeds, everything is unreachable."""
    graph = nk.Graph(2, directed=True)
    graph.addEdge(0, 1)
    
    result = compute_click_depth(graph, hub_seeds=[])
    assert result[0]["inbound_reachable"] is False
    assert result[0]["depth"] == UNREACHABLE_DEPTH
    assert result[1]["inbound_reachable"] is False
    assert result[1]["depth"] == UNREACHABLE_DEPTH
