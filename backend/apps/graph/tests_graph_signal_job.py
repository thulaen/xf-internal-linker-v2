import pytest

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink, GraphSignalRun
from apps.graph.services.graph_signal_job import load_active_edges, compute_graph_hash, run_signals

pytestmark = pytest.mark.django_db

def _create_content_item(url_suffix=""):
    return ContentItem.objects.create(
        url=f"https://example.com/page{url_suffix}",
        title=f"Test Page {url_suffix}",
        content_hash=f"hash{url_suffix}",
        content_id=int(url_suffix) if url_suffix.isdigit() else 1,
        is_deleted=False
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
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    run, graph_data = run_signals(signal_version="v1.0")
    assert run.status == GraphSignalRun.STATUS_COMPUTING
    assert run.node_count == 2
    assert run.edge_count == 1
    assert graph_data is not None
    
def test_run_signals_unchanged_graph():
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    # First run creates the computing run
    run1, graph_data1 = run_signals(signal_version="v1.0")
    
    # Manually set to current
    run1.status = GraphSignalRun.STATUS_CURRENT
    run1.save()
    
    # Second run should skip
    run2, graph_data2 = run_signals(signal_version="v1.0")
        
    assert run2.id == run1.id
    assert graph_data2 is None

def test_run_signals_force():
    ci1 = _create_content_item("1")
    ci2 = _create_content_item("2")
    ExistingLink.objects.create(from_content_item=ci1, to_content_item=ci2, anchor_text="a")
    
    run1, _ = run_signals(signal_version="v1.0")
    run1.status = GraphSignalRun.STATUS_CURRENT
    run1.save()
    
    run2, graph_data2 = run_signals(force=True, signal_version="v1.0")
    assert run2.id != run1.id
    assert run2.status == GraphSignalRun.STATUS_COMPUTING
    assert graph_data2 is not None
