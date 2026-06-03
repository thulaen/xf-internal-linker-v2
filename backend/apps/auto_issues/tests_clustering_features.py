"""Unit tests for clustering feature-hash extraction (pure, no DB)."""
from django.test import SimpleTestCase

from apps.auto_issues.services.clustering_features import feature_hashes


class FeatureHashesTests(SimpleTestCase):
    def test_deterministic(self):
        a = feature_hashes("connection timeout on node", "stack trace", ["a/b.py"])
        b = feature_hashes("connection timeout on node", "stack trace", ["a/b.py"])
        self.assertEqual(a, b)

    def test_numeric_variants_share_features(self):
        a = set(feature_hashes("timeout after 1234 ms on the worker pool"))
        b = set(feature_hashes("timeout after 9999 ms on the worker pool"))
        self.assertTrue(a & b, "normalised numeric variants should share features")

    def test_paths_contribute_features(self):
        without = set(feature_hashes("same text body here now please"))
        with_path = set(feature_hashes("same text body here now please", paths=["backend/x.py"]))
        self.assertTrue(with_path - without, "path should add a feature")

    def test_short_text_still_yields_one_feature(self):
        self.assertEqual(len(feature_hashes("oops", k=5)), 1)

    def test_empty_yields_no_features(self):
        self.assertEqual(feature_hashes("", "", []), [])

    def test_features_are_u64(self):
        for h in feature_hashes("alpha beta gamma delta epsilon zeta"):
            self.assertGreaterEqual(h, 0)
            self.assertLess(h, 1 << 64)
