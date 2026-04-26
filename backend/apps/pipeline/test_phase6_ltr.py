"""Phase 6.4 — Node2Vec (#37) + BPR (#38) + FM (#39) wrapper tests."""

from __future__ import annotations


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
        result = factorization_machines.predict([{"feature1": 1.0, "feature2": 0.5}])
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
        """Hand-rolled NumPy FM trains a regression model + scores back."""
        import os
        import tempfile

        from apps.core.models import AppSetting

        # Synthetic target: y = a + b. Linear-only.
        rng_features = []
        rng_targets = []
        import random

        rng = random.Random(0)
        for _ in range(200):
            a = rng.uniform(0, 1)
            b = rng.uniform(0, 1)
            rng_features.append({"a": a, "b": b})
            rng_targets.append(a + b)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fm.pkl")
            ok = factorization_machines.fit_and_save(
                features=rng_features,
                targets=rng_targets,
                output_path=path,
                factors=4,
                num_iter=30,
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
            # Sanity: zero input → near zero; bigger input → bigger pred.
            self.assertLess(abs(preds[1]), 0.4)
            self.assertGreater(preds[0], preds[1])

    def test_fit_learns_pairwise_interaction_better_than_linear_only(self) -> None:
        """Distinguishes a real FM from a linear-only baseline.

        Synthetic target: y = a XOR b (in continuous form: y = (a-b)^2).
        A linear regressor cannot fit XOR (the classic 1969 Minsky-Papert
        critique). A real FM with rank ≥ 1 should fit it via the
        pairwise term. Rendle 2010 §3.2 uses XOR-like cases as the
        canonical demonstration of FM expressiveness.

        Tests the *pairwise* term specifically — a linear-only FM
        (factors=0 or all zero V) would have ~uniform predictions
        regardless of input, scoring much worse than a real FM.
        """
        import os
        import tempfile

        import numpy as np
        from apps.core.models import AppSetting

        # Generate a balanced set of (a, b) ∈ {(0,0), (0,1), (1,0), (1,1)}
        # with continuous noise + the XOR-like target (a-b)^2:
        # (0,0) → 0, (0,1) → 1, (1,0) → 1, (1,1) → 0.
        # No linear combination of (a, b) can fit this — needs the
        # interaction term a*b.
        rng = np.random.default_rng(0)
        features = []
        targets = []
        for _ in range(200):
            a = float(rng.choice([0, 1])) + 0.05 * rng.normal()
            b = float(rng.choice([0, 1])) + 0.05 * rng.normal()
            features.append({"a": a, "b": b})
            targets.append((a - b) ** 2)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fm_xor.pkl")
            ok = factorization_machines.fit_and_save(
                features=features,
                targets=targets,
                output_path=path,
                factors=4,
                num_iter=80,
                learning_rate=0.05,
                task="regression",
            )
            self.assertTrue(ok)
            AppSetting.objects.update_or_create(
                key=factorization_machines.KEY_MODEL_PATH,
                defaults={"value": path, "description": ""},
            )
            # The four canonical XOR points.
            preds = factorization_machines.predict(
                [
                    {"a": 0.0, "b": 0.0},  # target 0
                    {"a": 0.0, "b": 1.0},  # target 1
                    {"a": 1.0, "b": 0.0},  # target 1
                    {"a": 1.0, "b": 1.0},  # target 0
                ]
            )
            self.assertIsNotNone(preds)

            # FM should rank the diagonal (a == b → target 0) BELOW
            # the off-diagonal (a != b → target 1). A linear-only
            # model cannot — it would need to put (1,1) above (0,0)
            # AND below (0,1) simultaneously, which no linear function
            # can.
            same_avg = (preds[0] + preds[3]) / 2.0  # both (a==b)
            diff_avg = (preds[1] + preds[2]) / 2.0  # both (a!=b)
            self.assertGreater(
                diff_avg - same_avg,
                0.3,
                f"FM did not learn the pairwise interaction: "
                f"same={same_avg:.3f} vs diff={diff_avg:.3f}. "
                "A linear-only model fails this check by construction.",
            )
            # Also assert the residual MSE is below what a linear-only
            # baseline (mean(y) ≈ 0.5) would achieve.
            mse_fm = (
                sum((p - t) ** 2 for p, t in zip(preds, [0.0, 1.0, 1.0, 0.0])) / 4.0
            )
            mse_baseline = sum((0.5 - t) ** 2 for t in [0.0, 1.0, 1.0, 0.0]) / 4.0
            self.assertLess(
                mse_fm,
                mse_baseline,
                f"FM MSE {mse_fm:.3f} should beat the constant-mean "
                f"baseline {mse_baseline:.3f}.",
            )
