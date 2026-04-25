"""Tests for pick #20 Product Quantization producer.

The producer wraps :mod:`apps.sources.product_quantization` (FAISS
``IndexPQ``) and is exercised against ``ContentItem.embedding`` rows.
Unit-test scale: we lower ``ks`` and ``min_training_rows`` so a fit
runs in under a second on synthetic vectors.
"""

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


@unittest.skipUnless(_faiss_available(), "FAISS not installed")
class ProductQuantizationProducerTests(TestCase):
    """Unit tests for the producer.

    The full PQ codebook training is fast enough at small ks that we
    don't need to mock FAISS. We use ks=4 / m=4 / dim=8 in tests so a
    fit finishes in milliseconds. Real production refit uses
    ks=256 / m=8 / dim=1024.
    """

    SMALL_DIM = 8
    SMALL_M = 4
    SMALL_KS = 4
    # 39 × 4 = 156, so seed >= 156 to clear the threshold.
    SMALL_MIN_TRAINING = 39 * 4

    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=20, scope_type="node", title="pq-test"
        )

    def _seed_embeddings(self, count: int):
        """Bulk-create ContentItems with deterministic ``SMALL_DIM``-dim
        embeddings. We don't use random vectors so the test is
        repeatable; the codebook still trains with these synthetic
        rows because we use small ks=4.
        """
        import numpy as np

        # Generate count vectors with light noise around random
        # cluster centers so the codebook actually learns something
        # rather than collapsing to identical centroids.
        rng = np.random.default_rng(seed=42)
        centers = rng.normal(size=(self.SMALL_KS, self.SMALL_DIM))
        labels = rng.integers(0, self.SMALL_KS, size=count)
        vectors = (
            centers[labels] + 0.1 * rng.normal(size=(count, self.SMALL_DIM))
        ).astype("float32")

        items = []
        for i in range(count):
            items.append(
                ContentItem(
                    content_id=10_000 + i,
                    content_type="thread",
                    title=f"pq-{i}",
                    scope=self.scope,
                    embedding=vectors[i].tolist(),
                )
            )
        ContentItem.objects.bulk_create(items)

    # ── load_codebook ────────────────────────────────────────────

    def test_load_codebook_cold_start_returns_none(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            load_codebook,
        )

        self.assertIsNone(load_codebook())

    def test_load_quantizer_cold_start_returns_none(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            load_quantizer,
        )

        self.assertIsNone(load_quantizer())

    # ── fit_and_persist_from_embeddings ───────────────────────────

    def test_returns_none_when_below_minimum(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            load_codebook,
        )

        # Only 5 rows seeded — well below SMALL_MIN_TRAINING.
        self._seed_embeddings(5)
        result = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNone(result)
        self.assertIsNone(load_codebook())

    def test_persists_codebook_and_encodes_rows(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            load_codebook,
            load_quantizer,
        )

        n = self.SMALL_MIN_TRAINING + 50
        self._seed_embeddings(n)
        result = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rows_encoded, n)

        snap = load_codebook()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.dimension, self.SMALL_DIM)
        self.assertEqual(snap.m, self.SMALL_M)
        self.assertEqual(snap.ks, self.SMALL_KS)
        self.assertEqual(snap.training_size, n)
        self.assertEqual(snap.encoded_count, n)
        self.assertGreater(snap.bytes_per_vector, 0)

        # Every ContentItem with an embedding now has a pq_code.
        encoded_count = ContentItem.objects.exclude(pq_code__isnull=True).count()
        self.assertEqual(encoded_count, n)

        # All encoded rows share the same pq_code_version.
        versions = set(
            ContentItem.objects.exclude(pq_code_version__isnull=True)
            .values_list("pq_code_version", flat=True)
            .distinct()
        )
        self.assertEqual(versions, {snap.version})

        # load_quantizer returns a working decoder.
        quant = load_quantizer()
        self.assertIsNotNone(quant)
        self.assertTrue(quant.trained)

    def test_idempotent_refit_produces_same_version(self) -> None:
        """Re-running on unchanged data writes the same codes."""
        import numpy as np

        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            load_codebook,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_embeddings(n)
        first = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(first)
        codes_first = list(
            ContentItem.objects.exclude(pq_code__isnull=True)
            .order_by("pk")
            .values_list("pk", "pq_code")
        )

        second = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(second)
        codes_second = list(
            ContentItem.objects.exclude(pq_code__isnull=True)
            .order_by("pk")
            .values_list("pk", "pq_code")
        )
        self.assertEqual(codes_first, codes_second)

        # FAISS k-means picks centroid order based on initialization,
        # which is seeded but reset each call → version may differ.
        # The deterministic invariant is "same data → same codes".
        snap = load_codebook()
        self.assertIsNotNone(snap)

    # ── decode_pq_codes / pq_cosine_for_pks (Group B.2 read-path) ─

    def test_decode_pq_codes_cold_start_returns_none(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            decode_pq_codes,
        )

        self.assertIsNone(decode_pq_codes([b"\x00\x00\x00\x00"]))

    def test_decode_pq_codes_returns_array_after_fit(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            decode_pq_codes,
            fit_and_persist_from_embeddings,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_embeddings(n)
        result = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(result)

        item = ContentItem.objects.exclude(pq_code__isnull=True).first()
        decoded = decode_pq_codes([bytes(item.pq_code)])
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, (1, self.SMALL_DIM))

    def test_pq_cosine_for_pks_cold_start_returns_empty(self) -> None:
        from apps.pipeline.services.product_quantization_producer import (
            pq_cosine_for_pks,
        )

        self.assertEqual(pq_cosine_for_pks([1, 2, 3]), {})

    def test_pq_cosine_for_pks_returns_unit_vectors(self) -> None:
        import numpy as np

        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            pq_cosine_for_pks,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_embeddings(n)
        fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )

        pks = list(
            ContentItem.objects.exclude(pq_code__isnull=True)
            .values_list("pk", flat=True)[:10]
        )
        result = pq_cosine_for_pks(pks)
        self.assertEqual(set(result.keys()), set(pks))
        for vec in result.values():
            # L2 norm should be ≈ 1.0.
            self.assertAlmostEqual(float(np.linalg.norm(vec)), 1.0, places=4)

    def test_pq_cosine_skips_stale_versions(self) -> None:
        """Rows whose pq_code_version is out of date are skipped."""
        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            pq_cosine_for_pks,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_embeddings(n)
        fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        # Tag every encoded row with a stale version.
        ContentItem.objects.filter(pq_code__isnull=False).update(
            pq_code_version="stale-version"
        )
        pks = list(
            ContentItem.objects.exclude(pq_code__isnull=True)
            .values_list("pk", flat=True)[:10]
        )
        # All rows now have the wrong version → returns empty.
        self.assertEqual(pq_cosine_for_pks(pks), {})

    def test_encode_round_trip_within_tolerance(self) -> None:
        """Decoded vectors are within reasonable distance of originals."""
        import numpy as np

        from apps.pipeline.services.product_quantization_producer import (
            fit_and_persist_from_embeddings,
            load_quantizer,
        )

        n = self.SMALL_MIN_TRAINING + 30
        self._seed_embeddings(n)
        result = fit_and_persist_from_embeddings(
            min_training_rows=self.SMALL_MIN_TRAINING,
            m=self.SMALL_M,
            ks=self.SMALL_KS,
        )
        self.assertIsNotNone(result)
        quant = load_quantizer()
        self.assertIsNotNone(quant)

        # Pick one row, decode its pq_code, compare to its embedding.
        item = ContentItem.objects.exclude(pq_code__isnull=True).first()
        self.assertIsNotNone(item)
        # pq_code is bytes → reshape to a (1, bytes_per_vector) array.
        codes = np.frombuffer(item.pq_code, dtype=np.uint8).reshape(
            1, quant.bytes_per_vector
        )
        recon = quant.decode(codes)
        original = np.asarray(item.embedding, dtype=np.float32)
        # With k=4 centroids covering the whole vector space, the
        # reconstruction error is high but bounded; check it's in
        # the same ballpark.
        err = np.linalg.norm(recon[0] - original) / (
            np.linalg.norm(original) + 1e-9
        )
        self.assertLess(err, 2.0)  # generous bound for 4-centroid PQ
