"""Unit tests for the pure scoring core of the tuning corpus (no I/O)."""
from django.test import SimpleTestCase

from apps.auto_issues.services.sample_corpus import cluster_pairs, precision_recall


class ClusterPairsTests(SimpleTestCase):
    def test_orders_each_pair(self):
        self.assertEqual(
            cluster_pairs(["b", "a", "c"]),
            [("a", "b"), ("b", "c"), ("a", "c")],
        )

    def test_singleton_has_no_pairs(self):
        self.assertEqual(cluster_pairs(["x"]), [])


class PrecisionRecallTests(SimpleTestCase):
    def test_perfect_clustering(self):
        labels = {"1": "A", "2": "A", "3": "B"}
        p, r = precision_recall([["1", "2"], ["3"]], labels)
        self.assertEqual((p, r), (1.0, 1.0))

    def test_over_merge_lowers_precision(self):
        # Same namespace (gt:) so the cross-group merge counts as a false positive.
        labels = {"1": "gt:A", "2": "gt:A", "3": "gt:B"}
        # B merged into A's cluster: pairs (1,2)=tp, (1,3)=fp, (2,3)=fp
        p, r = precision_recall([["1", "2", "3"]], labels)
        self.assertAlmostEqual(p, 1 / 3)
        self.assertEqual(r, 1.0)

    def test_split_lowers_recall(self):
        labels = {"1": "A", "2": "A"}
        p, r = precision_recall([["1"], ["2"]], labels)
        self.assertEqual(r, 0.0)
        self.assertEqual(p, 1.0)  # no placed labeled pairs → precision defaults to 1

    def test_unlabeled_members_ignored(self):
        labels = {"1": "A", "2": "A"}
        p, r = precision_recall([["1", "2", "unlabeled-x"]], labels)
        self.assertEqual((p, r), (1.0, 1.0))

    def test_empty_labels(self):
        p, r = precision_recall([["1", "2"]], {})
        self.assertEqual((p, r), (1.0, 0.0))

    def test_cross_namespace_pairs_ignored(self):
        # gt: and fp: are different label systems — a cluster mixing one of each
        # is neither a hit nor a miss, so precision stays perfect.
        labels = {"1": "gt:5", "2": "gt:5", "3": "fp:abc"}
        p, r = precision_recall([["1", "2", "3"]], labels)
        self.assertEqual(p, 1.0)
        self.assertEqual(r, 1.0)

    def test_same_namespace_over_merge_is_false_positive(self):
        labels = {"1": "gt:5", "2": "gt:5", "3": "gt:9"}
        p, r = precision_recall([["1", "2", "3"]], labels)
        self.assertAlmostEqual(p, 1 / 3)  # (1,2)=tp, (1,3)&(2,3)=fp same ns
        self.assertEqual(r, 1.0)
