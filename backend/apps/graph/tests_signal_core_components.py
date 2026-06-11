import networkit as nk
from apps.graph.services.signals.core_components import compute_core_numbers, compute_components

def test_compute_core_numbers():
    # *Given* a 3-core embedded in a sparser graph
    G = nk.Graph(5, directed=False)
    # Complete graph on nodes 0, 1, 2, 3 -> 3-core
    G.addEdge(0, 1)
    G.addEdge(0, 2)
    G.addEdge(0, 3)
    G.addEdge(1, 2)
    G.addEdge(1, 3)
    G.addEdge(2, 3)
    # Node 4 is attached to node 0 -> 1-core
    G.addEdge(0, 4)
    
    # *When* k-core runs
    cores = compute_core_numbers(G)
    
    # *Then* the core nodes get core_number 3
    assert cores[0] >= 3
    assert cores[1] == 3
    assert cores[2] == 3
    assert cores[3] == 3
    assert cores[4] == 1

def test_compute_components():
    # *Given* two disconnected islands
    G = nk.Graph(4, directed=False)
    # Island 1: nodes 0, 1, 2
    G.addEdge(0, 1)
    G.addEdge(1, 2)
    # Island 2: node 3
    
    # *When* components run
    comps = compute_components(G)
    
    # *Then* they get different component ids and only the larger is is_main_component
    assert comps[0]["component_id"] == comps[1]["component_id"]
    assert comps[0]["component_id"] == comps[2]["component_id"]
    assert comps[3]["component_id"] != comps[0]["component_id"]
    
    assert comps[0]["is_main_component"] is True
    assert comps[1]["is_main_component"] is True
    assert comps[2]["is_main_component"] is True
    assert comps[3]["is_main_component"] is False
