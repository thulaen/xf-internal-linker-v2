"""Phase 6.4 — Node2Vec (#37) + BPR (#38) + FM (#39) wrapper tests."""

from __future__ import annotations

import unittest

from django.test import TestCase

from apps.pipeline.services import (
    bpr_ranking,
    factorization_machines,
    node2vec_embeddings,
)


class Node2VecEmbeddingsTests(TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(node2vec_embeddings.is_available(), bool)

    def test_load_cold_start_returns_empty(self) -> None:
        result = node2vec_embeddings.load_embeddings()
        self.assertTrue(result.is_empty)

    def test_vector_for_cold_start_returns_none(self) -> None:
        self.assertIsNone(node2vec_embeddings.vector_for("any-node"))

    def test_invalid_path_returns_empty(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=node2vec_embeddings.KEY_EMBEDDINGS_PATH,
            defaults={"value": "/tmp/no/file.pkl", "description": ""},
        )
        self.assertTrue(node2vec_embeddings.load_embeddings().is_empty)

    def test_fit_with_no_dep_returns_false(self) -> None:
        if node2vec_embeddings.HAS_NODE2VEC:
            self.skipTest("dep installed — cold-start test n/a")
        self.assertFalse(
            node2vec_embeddings.fit_and_save(
                edges=[(1, 2), (2, 3)], output_path="/tmp/x.pkl"
            )
        )

    def test_fit_with_no_edges_returns_false(self) -> None:
        self.assertFalse(
            node2vec_embeddings.fit_and_save(edges=[], output_path="/tmp/x.pkl")
        )


class BprRankingTests(TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(bpr_ranking.is_available(), bool)

    def test_load_cold_start_returns_empty(self) -> None:
        snap = bpr_ranking.load_snapshot()
        self.assertTrue(snap.is_empty)

    def test_score_cold_start_returns_none(self) -> None:
        result = bpr_ranking.score_for_user("u1", ["i1", "i2"])
        self.assertIsNone(result)

    def test_invalid_path_returns_empty(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=bpr_ranking.KEY_MODEL_PATH,
            defaults={"value": "/tmp/no/bpr.pkl", "description": ""},
        )
        self.assertTrue(bpr_ranking.load_snapshot().is_empty)

    def test_fit_below_min_interactions_returns_false(self) -> None:
        # < 5 interactions → skip.
        self.assertFalse(
            bpr_ranking.fit_and_save(
                interactions=[("u1", "i1", 1.0)],
                output_path="/tmp/bpr.pkl",
            )
        )


class FactorizationMachinesTests(TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(factorization_machines.is_available(), bool)

    def test_load_cold_start_returns_empty(self) -> None:
        self.assertTrue(factorization_machines.load_snapshot().is_empty)

    def test_predict_empty_features_returns_empty_list(self) -> None:
        self.assertEqual(factorization_machines.predict([]), [])

    def test_predict_cold_start_returns_none(self) -> None:
        result = factorization_machines.predict(
            [{"feature1": 1.0, "feature2": 0.5}]
        )
        self.assertIsNone(result)

    def test_invalid_path_returns_empty_snapshot(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=factorization_machines.KEY_MODEL_PATH,
            defaults={"value": "/tmp/no/fm.pkl", "description": ""},
        )
        self.assertTrue(factorization_machines.load_snapshot().is_empty)

    def test_fit_below_min_returns_false(self) -> None:
        self.assertFalse(
            factorization_machines.fit_and_save(
                features=[{"a": 1}],
                targets=[1.0],
                output_path="/tmp/fm.pkl",
            )
        )

    def test_fit_mismatched_lengths_returns_false(self) -> None:
        self.assertFalse(
            factorization_machines.fit_and_save(
                features=[{"a": i} for i in range(5)],
                targets=[1.0],  # length mismatch
                output_path="/tmp/fm.pkl",
            )
        )

    def test_fit_and_predict_round_trip_regression(self) -> None:
        """Hand-rolled NumPy FM trains a regression model + scores back.

        Real-data integration: the previously-skipped path now runs on
        every test because we no longer depend on a pip dep that may
        be missing.
        """
        import os
        import tempfile

        from apps.core.models import AppSetting

        # Synthetic regression target: y = a + b + 2*a*b
        # FM should learn the linear (a, b) and pairwise (a*b) terms.
        rng_features = []
        rng_targets = []
        import random

        rng = random.Random(0)
        for _ in range(200):
            a = rng.uniform(0, 1)
            b = rng.uniform(0, 1)
            rng_features.append({"a": a, "b": b})
            rng_targets.append(a + b + 2 * a * b)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fm.pkl")
            ok = factorization_machines.fit_and_save(
                features=rng_features,
                targets=rng_targets,
                output_path=path,
                factors=4,
                num_iter=20,
                learning_rate=0.05,
                task="regression",
            )
            self.assertTrue(ok)
            AppSetting.objects.update_or_create(
                key=factorization_machines.KEY_MODEL_PATH,
                defaults={"value": path, "description": ""},
            )
            preds = factorization_machines.predict(
                [{"a": 0.5, "b": 0.5}, {"a": 0.0, "b": 0.0}]
            )
            self.assertIsNotNone(preds)
            self.assertEqual(len(preds), 2)
            # The "a=0,b=0" prediction should be near 0 (target was 0
            # for that input class). Generous tolerance because 200
            # samples × 20 iterations is light.
            self.assertLess(abs(preds[1]), 0.6)
            # The "a=0.5,b=0.5" target was 0.5 + 0.5 + 0.5 = 1.5 — pred
            # should be on the positive side.
            self.assertGreater(preds[0], preds[1])
