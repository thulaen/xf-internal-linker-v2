import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.content.models import ContentItem
from apps.graph.models import (
    GraphSignalRun,
    NodeGraphSignal,
    LinkPredictionCandidate,
)

pytestmark = pytest.mark.django_db

def _create_content_item(url_suffix=""):
    return ContentItem.objects.create(
        url=f"https://example.com/page{url_suffix}",
        title=f"Test Page {url_suffix}",
        content_hash=f"hash{url_suffix}",
        content_id=int(url_suffix) if url_suffix.isdigit() else 1,
    )


def test_graph_signal_run_creation():
    run = GraphSignalRun.objects.create(
        graph_hash="a" * 64,
        signal_version="v1.0",
        node_count=100,
        edge_count=200,
        status=GraphSignalRun.STATUS_CURRENT,
        params_json={"config": "value"}
    )
    assert run.id is not None
    assert str(run) == f"Run aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa... (v1.0)"


def test_node_graph_signal_unique_constraint():
    run = GraphSignalRun.objects.create(
        graph_hash="b" * 64,
        signal_version="v1.0",
        node_count=1,
        edge_count=0,
        status=GraphSignalRun.STATUS_CURRENT,
        params_json={}
    )
    ci = _create_content_item("1")
    
    NodeGraphSignal.objects.create(
        run=run,
        content_item=ci,
        community_id=1,
        betweenness=0.5,
        click_depth=2,
        inbound_reachable=True,
        is_orphan=False,
        eigenvector=0.1,
        katz=0.2,
        closeness=0.3,
        core_number=3,
        component_id=1,
        is_main_component=True,
        local_clustering=0.8,
        group_seed_rank=1,
        node2vec_embedding=None
    )
    
    with pytest.raises(IntegrityError):
        NodeGraphSignal.objects.create(
            run=run,
            content_item=ci,
            community_id=2,
            betweenness=0.6,
            click_depth=1,
            inbound_reachable=True,
            is_orphan=False,
            eigenvector=0.2,
            katz=0.3,
            closeness=0.4,
            core_number=4,
            component_id=2,
            is_main_component=False,
            local_clustering=0.9,
            group_seed_rank=2,
            node2vec_embedding=None
        )


def test_link_prediction_candidate_creation():
    run = GraphSignalRun.objects.create(
        graph_hash="c" * 64,
        signal_version="v1.0",
        node_count=2,
        edge_count=0,
        status=GraphSignalRun.STATUS_CURRENT,
        params_json={}
    )
    ci_from = _create_content_item("2")
    ci_to = _create_content_item("3")
    
    cand = LinkPredictionCandidate.objects.create(
        run=run,
        from_item=ci_from,
        to_item=ci_to,
        adamic_adar=1.5,
        common_neighbors=2.0,
        jaccard=0.5,
        embed_cosine=0.9,
        same_community=True,
        is_bridge=False
    )
    assert cand.id is not None
    assert str(cand) == f"Candidate {ci_from} -> {ci_to}"
