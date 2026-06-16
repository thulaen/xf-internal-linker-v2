"""Tests for the graph API."""

from django.test import TestCase

from apps.content.models import ContentItem
from apps.graph.api import (
    current_icpc_degrees,
    current_node_communities,
    current_rgsd_density_gradients,
    current_sbma_blocks,
    current_tosd_lambdas,
    get_current_run,
    latest_node_signal,
    link_prediction_candidates,
)
from apps.graph.models import (
    GraphSignalRun,
    LinkPredictionCandidate,
    NodeGraphSignal,
)


class GraphAPITests(TestCase):
    def setUp(self):
        self.item1 = ContentItem.objects.create(content_id=1, content_type=1)
        self.item2 = ContentItem.objects.create(content_id=2, content_type=1)

    def test_no_run(self):
        """Test API when no current run exists."""
        self.assertIsNone(get_current_run())
        self.assertIsNone(latest_node_signal(self.item1))
        self.assertEqual(link_prediction_candidates(self.item1), [])

    def test_with_run(self):
        """Test API with a current run."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=2,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        
        node_sig = NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            core_number=2,
        )
        
        link_pred = LinkPredictionCandidate.objects.create(
            run=run,
            from_item=self.item1,
            to_item=self.item2,
            adamic_adar=0.8,
        )

        self.assertEqual(get_current_run(), run)
        self.assertEqual(latest_node_signal(self.item1), node_sig)
        self.assertIsNone(latest_node_signal(self.item2))
        
        preds_from = link_prediction_candidates(self.item1)
        self.assertEqual(len(preds_from), 1)
        self.assertEqual(preds_from[0], link_pred)

        preds_to = link_prediction_candidates(self.item2, as_destination=True)
        self.assertEqual(len(preds_to), 1)
        self.assertEqual(preds_to[0], link_pred)
        self.assertEqual(preds_to[0].from_item, self.item1)

    def test_current_node_communities_returns_current_run_map(self):
        """Given a current graph run, When callers ask for communities, Then keys are content keys."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=2,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            community_id=7,
        )

        self.assertEqual(current_node_communities(), {(self.item1.pk, "1"): 7})

    def test_current_icpc_degrees_returns_current_run_map(self):
        """Given a current graph run, When callers ask for ICPC counts, Then keys match content keys."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=2,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            icpc_local_indegree=2,
            icpc_global_indegree=3,
        )

        self.assertEqual(current_icpc_degrees(), {(self.item1.pk, "1"): (2, 3)})

    def test_current_sbma_blocks_returns_current_run_blocks_and_matrix(self):
        """Given a current run, When callers ask for SBMA blocks, Then the matrix is parsed."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=1,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
            sbma_matrix_json={"0:1": 0.75},
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            community_id=1,
            sbma_block_id=0,
        )

        blocks, matrix = current_sbma_blocks()

        self.assertEqual(blocks, {(self.item1.pk, "1"): 0})
        self.assertEqual(matrix, {(0, 1): 0.75})

    def test_current_tosd_lambdas_returns_current_run_values(self):
        """Given a current run, When callers ask for TOSD, Then stored values are returned."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=1,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            community_id=1,
            tosd_lambda=0.25,
        )

        self.assertEqual(current_tosd_lambdas(), {(self.item1.pk, "1"): 0.25})

    def test_current_rgsd_density_gradients_returns_current_local_density(self):
        """Given a current run, When callers ask for RGSD, Then stored density is returned."""
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=1,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=self.item1,
            community_id=1,
            local_clustering=0.4,
        )

        self.assertEqual(current_rgsd_density_gradients(), {(self.item1.pk, "1"): 0.4})
