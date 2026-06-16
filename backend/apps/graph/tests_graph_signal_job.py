import pytest
from datetime import timedelta
from django.utils import timezone

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink, GraphSignalRun, NodeGraphSignal, LinkPredictionCandidate
from apps.graph.services.graph_signal_job import (
    _compute_icpc_degrees,
    _compute_sbma_blocks,
    load_active_edges,
    compute_graph_hash,
    run_signals,
)

pytestmark = pytest.mark.django_db

def _create_content_item(url_suffix=""):
    return ContentItem.objects.create(
        url=f"https://example.com/page{url_suffix}",
        title=f"Test Page {url_suffix}",
        content_hash=f"hash{url_suffix}",
        content_id=int(url_suffix) if url_suffix.isdigit() else 1,
        is_deleted=False,
        march_2026_pagerank_score=0.5
    )

def test_load_active_edges():
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ci3 = _create_content_item("3")
    
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    ExistingLink.objects.create(from_content_item=ci2, to_content_item=ci3, anchor_text="b")
    
    # ci4 is deleted, so it shouldn't be included
    ci4 = _create_content_item("4")
    ci4.is_deleted = True
    ci4.save()
    ExistingLink.objects.create(from_content_item=ci3, to_content_item=ci4, anchor_text="c")
    
    edges, extra_nodes = load_active_edges()
    
    # Only edges where both nodes are active should be returned
    assert (ci1.id, ci2.id) in edges
    assert (ci2.id, ci3.id) in edges
    assert (ci3.id, ci4.id) not in edges
    assert len(edges) == 2
    
    # All extra_nodes should be active
    assert set(extra_nodes) == {ci1.id, ci2.id, ci3.id}

def test_run_signals_changed_graph():
    """Given a changed graph, When the job runs, Then a current run with all signals exists and the prior run is superseded."""
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    # Run 1
    run, graph_data = run_signals(signal_version="v1.0")
    assert run.status == GraphSignalRun.STATUS_CURRENT
    assert run.node_count == 2
    assert run.edge_count == 1
    assert NodeGraphSignal.objects.filter(run=run).count() == 2
    
    # Run 2 with changed graph
    ci3 = _create_content_item("3")
    ExistingLink.objects.create(from_content_item=ci2, to_content_item=ci3, anchor_text="b")
    
    run2, graph_data2 = run_signals(signal_version="v1.0")
    assert run2.status == GraphSignalRun.STATUS_CURRENT
    assert run2.node_count == 3
    
    # Run 1 should be superseded
    run.refresh_from_db()
    assert run.status == GraphSignalRun.STATUS_SUPERSEDED

def test_run_signals_unchanged_graph():
    """Given the same graph, When the job re-runs, Then it no-ops."""
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    run1, graph_data1 = run_signals(signal_version="v1.0")
    
    # Second run should skip (no-op)
    run2, graph_data2 = run_signals(signal_version="v1.0")
        
    assert run2.id == run1.id
    assert graph_data2 is None
    assert run1.status == GraphSignalRun.STATUS_CURRENT

def test_retention_policy_pruning():
    """Given runs older than retention, When the job completes, Then they are pruned."""
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    # Create 3 older superseded runs
    now = timezone.now()
    r1 = GraphSignalRun.objects.create(graph_hash="h1", signal_version="v1.0", node_count=0, edge_count=0, status=GraphSignalRun.STATUS_SUPERSEDED, computed_at=now - timedelta(days=5))
    r2 = GraphSignalRun.objects.create(graph_hash="h2", signal_version="v1.0", node_count=0, edge_count=0, status=GraphSignalRun.STATUS_SUPERSEDED, computed_at=now - timedelta(days=4))
    r3 = GraphSignalRun.objects.create(graph_hash="h3", signal_version="v1.0", node_count=0, edge_count=0, status=GraphSignalRun.STATUS_SUPERSEDED, computed_at=now - timedelta(days=3))
    
    run4, graph_data4 = run_signals(signal_version="v1.0")
    
    # Prune keeps the 2 most recent superseded. r1 should be deleted.
    assert not GraphSignalRun.objects.filter(id=r1.id).exists()
    assert GraphSignalRun.objects.filter(id=r2.id).exists()
    assert GraphSignalRun.objects.filter(id=r3.id).exists()
    assert GraphSignalRun.objects.filter(id=run4.id).exists()

def test_dry_run():
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    run, graph_data = run_signals(signal_version="v1.0", dry_run=True)
    
    # Dry run deletes the created run object
    assert not GraphSignalRun.objects.filter(id=run.id).exists()
    assert NodeGraphSignal.objects.count() == 0


def test_compute_icpc_degrees_respects_community_size_floor():
    """Given graph communities, When ICPC counts run, Then small communities get no local count."""
    local, global_ = _compute_icpc_degrees(
        edges=[(1, 3), (2, 3), (4, 3)],
        id_to_idx={1: 0, 2: 1, 3: 2, 4: 3},
        community_ids={0: 10, 1: 10, 2: 10, 3: 20},
        min_community_size=3,
    )

    assert global_[2] == 3
    assert local[2] == 2

    local_small, _ = _compute_icpc_degrees(
        edges=[(1, 3), (2, 3)],
        id_to_idx={1: 0, 2: 1, 3: 2},
        community_ids={0: 10, 1: 10, 2: 10},
        min_community_size=4,
    )

    assert local_small.get(2, 0) == 0


def test_compute_sbma_blocks_returns_known_transition_probabilities():
    """Given block assignments, When SBMA runs, Then block probabilities match observed links."""
    blocks, matrix = _compute_sbma_blocks(
        edges=[(1, 2), (1, 3), (4, 3)],
        id_to_idx={1: 0, 2: 1, 3: 2, 4: 3},
        community_ids={0: 10, 1: 20, 2: 20, 3: 10},
        num_blocks=2,
    )

    assert blocks == {0: 0, 1: 1, 2: 1, 3: 0}
    assert matrix[(0, 1)] == 1.0
    assert matrix[(1, 1)] == 0.0


def test_compute_sbma_blocks_respects_single_block_limit():
    """Given one configured block, When SBMA runs, Then every page uses block zero."""
    blocks, matrix = _compute_sbma_blocks(
        edges=[(1, 2), (3, 4)],
        id_to_idx={1: 0, 2: 1, 3: 2, 4: 3},
        community_ids={0: 10, 1: 20, 2: 30, 3: 40},
        num_blocks=1,
    )

    assert set(blocks.values()) == {0}
    assert set(matrix) == {(0, 0)}
