"""Tests for ``pq_pairwise_similarity_above`` (Final.4)."""

from __future__ import annotations

import unittest

from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401

        return True
    except ImportError:
        return False


class PqPairwiseSimilarityTests(TestCase):
    SMALL_DIM = 8
    SMALL_M = 4
    SMALL_KS = 4
    SMALL_MIN_TRAINING = 39 * 4

    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=20, scope_type="node", title="pq-pairwise"
        )

    def _seed_clustered_embeddings(self, *, count: int):
        """Seed *count* ContentItems with embeddings from 3 tight clusters
        plus noise. After PQ training, items in the same source cluster
        should have very high pairwise PQ-cosine."""
        import numpy as np

        rng = np.random.default_rng(seed=1234)
        # Three cluster centres (well separated in 8-dim space).
        centres = np.array(
            [
                [1, 0, 0, 0, 1, 0, 0, 0],
                [0, 1, 0, 0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0, 0, 1, 0],
            ],
            dtype="float32",
        )
        labels = rng.integers(0, 3, size=count)
        # Tiny per-item noise so PQ has something to quantise.
        vectors = (centres[labels] + 0.05 * rng.normal(size=(count, self.SMALL_DIM))).astype(
            "float32"
        )
        items = []
        self._cluster_ids: list[int] = []
        for i in range(count):
            items.append(
                ContentItem(
                    content_id=20_000 + i,
                    content_type="thread",
                    title=f"pair-{i}",
                    scope=self.scope,
                    embedding=vectors[i].tolist(),
                )
            )
            self._cluster_ids.append(int(labels[i]))
        ContentItem.objects.bulk_create(items)

    def test_cold_start_returns_empty(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            pq_pairwise_similarity_above,
        )

        self.assertEqual(pq_pairwise_similarity_above([]), [])
        self.assertEqual(pq_pairwise_similarity_above([1, 2, 3]), [])

    def test_zero_threshold_returns_empty(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            pq_pairwise_similarity_above,
        )

        self.assertEqual(
            pq_pairwise_similarity_above([1, 2, 3], threshold=0.0), []
        )

    @unittest.skipUnless(_faiss_available(), "FAISS not installed")
    def test_finds_pairs_in_same_synthetic_cluster(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            pq_pairwise_similarity_above,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_clustered_embeddings(count=n)
        result = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(result)

        all_pks = list(
            ContentItem.objects.exclude(pq_code__isnull=True).values_list(
                "pk", flat=True
            )
        )
        # PQ at small ks=4 is noisy — drop the threshold so we
        # exercise the helper without fighting the synthetic
        # quantiser's resolution.
        pairs = pq_pairwise_similarity_above(all_pks, threshold=0.5)
        # We expect at least *some* pairs returned — many same-cluster
        # items should land above the threshold even with a tiny ks.
        self.assertGreater(len(pairs), 0)
        for a, b, score in pairs:
            self.assertLess(a, b, "pairs should be canonically ordered")
            self.assertGreaterEqual(score, 0.5)

    @unittest.skipUnless(_faiss_available(), "FAISS not installed")
    def test_high_threshold_returns_fewer_pairs(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            pq_pairwise_similarity_above,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_clustered_embeddings(count=n)
        fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        all_pks = list(
            ContentItem.objects.exclude(pq_code__isnull=True).values_list(
                "pk", flat=True
            )
        )
        loose = pq_pairwise_similarity_above(all_pks, threshold=0.3)
        strict = pq_pairwise_similarity_above(all_pks, threshold=0.95)
        self.assertGreaterEqual(len(loose), len(strict))


class ClusteringPqPrefilterTests(TestCase):
    """End-to-end opt-in: the clustering service can use PQ as a
    pre-filter before pgvector confirmation."""

    def test_prefilter_disabled_by_default(self) -> None:
        from apps.content.services.clustering import _pq_prefilter_enabled

        self.assertFalse(_pq_prefilter_enabled())

    def test_prefilter_flag_round_trip(self) -> None:
        from apps.content.services.clustering import (
            KEY_PQ_PREFILTER_ENABLED,
            _pq_prefilter_enabled,
        )
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_PQ_PREFILTER_ENABLED,
            defaults={"value": "true", "description": ""},
        )
        self.assertTrue(_pq_prefilter_enabled())

        AppSetting.objects.update_or_create(
            key=KEY_PQ_PREFILTER_ENABLED,
            defaults={"value": "no", "description": ""},
        )
        self.assertFalse(_pq_prefilter_enabled())

    def test_prefilter_returns_none_when_codebook_missing(self) -> None:
        """No codebook → method returns None → caller falls back to pgvector."""
        from apps.content.models import ContentItem, ScopeItem
        from apps.content.services.clustering import ClusteringService

        scope = ScopeItem.objects.create(
            scope_id=99, scope_type="node", title="prefilter"
        )
        item = ContentItem.objects.create(
            content_id=999,
            content_type="thread",
            title="t",
            scope=scope,
        )
        svc = ClusteringService()
        # No codebook persisted → None.
        self.assertIsNone(svc._pq_prefilter_candidates(item))

    def test_prefilter_returns_none_when_item_unencoded(self) -> None:
        """Codebook persisted but item has no pq_code → None (fallback path)."""
        from apps.content.models import ContentItem, ScopeItem
        from apps.content.services.clustering import ClusteringService
        from apps.core.models import AppSetting
        from apps.pipeline.services.product_quantization_producer import (
            KEY_CODEBOOK,
            KEY_DIMENSION,
            KEY_M,
            KEY_KS,
            KEY_VERSION,
            KEY_BYTES_PER_VECTOR,
        )

        # Persist enough fake codebook metadata for load_codebook() to
        # return a CodebookSnapshot (we don't need the codebook itself
        # to fire — _pq_prefilter_candidates short-circuits earlier on
        # the item's missing pq_code).
        for key, value in (
            (KEY_CODEBOOK, ""),
            (KEY_DIMENSION, "8"),
            (KEY_M, "4"),
            (KEY_KS, "4"),
            (KEY_VERSION, "abc123"),
            (KEY_BYTES_PER_VECTOR, "4"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )
        scope = ScopeItem.objects.create(
            scope_id=99, scope_type="node", title="prefilter"
        )
        item = ContentItem.objects.create(
            content_id=999,
            content_type="thread",
            title="t",
            scope=scope,
            pq_code=None,
            pq_code_version=None,
        )
        svc = ClusteringService()
        self.assertIsNone(svc._pq_prefilter_candidates(item))
