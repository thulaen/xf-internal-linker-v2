"""TDD for the NetworKit graph builder (Phase NK foundation).

Pure-function tests over tiny hand-built edge lists with known expected structure —
no DB, no Django app state needed.
"""
from __future__ import annotations

try:
    import networkit as nk
    from apps.graph.services.networkit_graph import build_nk_graph
    HAS_NK = True
except ImportError:
    HAS_NK = False


def test_build_maps_sparse_ids_to_dense_directed_graph():
    g, id_to_idx, idx_to_id = build_nk_graph([(10, 20), (20, 30), (10, 30)])
    assert g.isDirected()
    assert g.numberOfNodes() == 3
    assert g.numberOfEdges() == 3
    # the mapping is a bijection over the three ids
    assert sorted(idx_to_id) == [10, 20, 30]
    assert idx_to_id[id_to_idx[30]] == 30
    # direction is preserved: 10->20 exists, 20->10 does not
    assert g.hasEdge(id_to_idx[10], id_to_idx[20])
    assert not g.hasEdge(id_to_idx[20], id_to_idx[10])


def test_build_skips_self_loops_and_collapses_duplicates():
    g, _, _ = build_nk_graph([(1, 1), (1, 2), (1, 2), (2, 2)])
    assert g.numberOfNodes() == 2          # ids 1 and 2
    assert g.numberOfEdges() == 1          # only 1->2, once (self-loops + dup dropped)


def test_build_includes_isolated_extra_nodes_as_orphans():
    g, id_to_idx, _ = build_nk_graph([(1, 2)], extra_nodes=[1, 2, 99])
    assert g.numberOfNodes() == 3          # 1, 2, and the orphan 99
    assert g.degreeOut(id_to_idx[99]) == 0 and g.degreeIn(id_to_idx[99]) == 0


def test_build_empty_graph_is_valid():
    g, id_to_idx, idx_to_id = build_nk_graph([])
    assert g.numberOfNodes() == 0
    assert g.numberOfEdges() == 0
    assert id_to_idx == {} and idx_to_id == []
