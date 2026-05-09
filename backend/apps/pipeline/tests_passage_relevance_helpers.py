"""Focused tests for the index-time helpers in ``passage_relevance``.

Each helper extracted from ``regenerate_passage_embeddings_for`` gets its
own test class. All tests use ``SimpleTestCase`` and ``unittest.mock`` so
the DB / native extensions / embedding model are never touched — what we
exercise here is the pure decision logic of each helper in isolation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services import passage_relevance as pr
from apps.sources.passages import Passage


def _make_passage(index: int, text: str, count: int = 5) -> Passage:
    return Passage(
        index=index,
        text=text,
        token_start=index * count,
        token_end=(index + 1) * count,
        token_count=count,
    )


def _make_resources(*, codebook=None, signature: str = "sig-v1") -> pr._EmbeddingResources:
    return pr._EmbeddingResources(
        model=MagicMock(name="model"),
        signature=signature,
        codebook=codebook,
        opq_version=getattr(codebook, "corpus_signature", "") if codebook else "",
    )


class ShouldIndexPassagesTests(SimpleTestCase):
    def test_returns_true_when_enabled_and_not_duplicate(self) -> None:
        item = SimpleNamespace(duplicate_of_id=None)
        with patch.object(pr, "_setting_bool", return_value=True):
            self.assertTrue(pr._should_index_passages(item))

    def test_returns_false_when_feature_flag_off(self) -> None:
        item = SimpleNamespace(duplicate_of_id=None)
        with patch.object(pr, "_setting_bool", return_value=False):
            self.assertFalse(pr._should_index_passages(item))

    def test_returns_false_when_item_is_duplicate(self) -> None:
        item = SimpleNamespace(duplicate_of_id=42)
        with patch.object(pr, "_setting_bool", return_value=True):
            self.assertFalse(pr._should_index_passages(item))


class SegmentPassagesFromPostTests(SimpleTestCase):
    def test_re_indexes_contiguously_from_zero(self) -> None:
        post = SimpleNamespace(
            clean_text="One sentence. Two sentence. Three sentence."
        )
        fake_segments = [
            SimpleNamespace(text="A", token_start=0, token_end=2, token_count=2),
            SimpleNamespace(text="B", token_start=2, token_end=4, token_count=2),
            SimpleNamespace(text="C", token_start=4, token_end=6, token_count=2),
        ]
        with (
            patch.object(pr, "_setting_int", side_effect=[200, 0]),
            patch.object(pr, "_split_into_sentences", return_value=["x"]),
            patch(
                "apps.sources.passages.segment_from_sentences",
                return_value=fake_segments,
            ),
        ):
            out = pr._segment_passages_from_post(post)

        self.assertEqual([p.index for p in out], [0, 1, 2])
        self.assertEqual([p.text for p in out], ["A", "B", "C"])

    def test_caps_to_max_passages_when_setting_positive(self) -> None:
        post = SimpleNamespace(clean_text="text")
        full = [
            SimpleNamespace(text=f"S{i}", token_start=i, token_end=i + 1, token_count=1)
            for i in range(10)
        ]
        with (
            patch.object(pr, "_setting_int", side_effect=[200, 4]),
            patch.object(pr, "_split_into_sentences", return_value=["x"]),
            patch(
                "apps.sources.passages.segment_from_sentences", return_value=full
            ),
        ):
            out = pr._segment_passages_from_post(post)

        self.assertEqual(len(out), 4)

    def test_returns_empty_when_segmenter_returns_empty(self) -> None:
        post = SimpleNamespace(clean_text="text")
        with (
            patch.object(pr, "_setting_int", side_effect=[200, 0]),
            patch.object(pr, "_split_into_sentences", return_value=[]),
            patch(
                "apps.sources.passages.segment_from_sentences", return_value=[]
            ),
        ):
            self.assertEqual(pr._segment_passages_from_post(post), [])


class DiffPassagesTests(SimpleTestCase):
    def test_all_unchanged_returns_empty_when_no_codebook(self) -> None:
        passages = [_make_passage(0, "A"), _make_passage(1, "B")]
        hashes = ["h0", "h1"]
        existing = {
            0: SimpleNamespace(
                embedding=[0.1] * 4,
                embedding_text_hash="h0",
                embedding_model_version="sig-v1",
                opq_codebook_version="",
                opq_code=None,
            ),
            1: SimpleNamespace(
                embedding=[0.2] * 4,
                embedding_text_hash="h1",
                embedding_model_version="sig-v1",
                opq_codebook_version="",
                opq_code=None,
            ),
        }
        diff = pr._diff_passages(passages, hashes, existing, _make_resources())

        self.assertEqual(diff.embed_indices, [])
        self.assertEqual(diff.embed_texts, [])
        self.assertEqual(diff.opq_indices, [])

    def test_changed_hash_flags_for_re_embed(self) -> None:
        passages = [_make_passage(0, "A"), _make_passage(1, "B-NEW")]
        hashes = ["h0", "h1-new"]
        existing = {
            0: SimpleNamespace(
                embedding=[0.1],
                embedding_text_hash="h0",
                embedding_model_version="sig-v1",
                opq_codebook_version="",
                opq_code=None,
            ),
            1: SimpleNamespace(
                embedding=[0.2],
                embedding_text_hash="h1-OLD",
                embedding_model_version="sig-v1",
                opq_codebook_version="",
                opq_code=None,
            ),
        }
        diff = pr._diff_passages(passages, hashes, existing, _make_resources())

        self.assertEqual(diff.embed_indices, [1])
        self.assertEqual(diff.embed_texts, ["B-NEW"])

    def test_opq_version_mismatch_flags_for_re_encode_only(self) -> None:
        passages = [_make_passage(0, "A")]
        hashes = ["h0"]
        codebook = SimpleNamespace(corpus_signature="opq-v2")
        existing = {
            0: SimpleNamespace(
                embedding=[0.1],
                embedding_text_hash="h0",
                embedding_model_version="sig-v1",
                opq_codebook_version="opq-OLD",
                opq_code=b"\x00" * 64,
            ),
        }
        resources = _make_resources(codebook=codebook)
        diff = pr._diff_passages(passages, hashes, existing, resources)

        self.assertEqual(diff.embed_indices, [])
        self.assertEqual(diff.opq_indices, [0])

    def test_missing_row_flags_for_both_embed_and_opq(self) -> None:
        passages = [_make_passage(0, "A")]
        hashes = ["h0"]
        codebook = SimpleNamespace(corpus_signature="opq-v1")
        diff = pr._diff_passages(
            passages, hashes, existing={}, resources=_make_resources(codebook=codebook)
        )

        self.assertEqual(diff.embed_indices, [0])
        self.assertEqual(diff.opq_indices, [0])


class EncodePassageBatchTests(SimpleTestCase):
    def test_empty_text_list_returns_zero_shape(self) -> None:
        out = pr._encode_passage_batch([], MagicMock())

        self.assertEqual(out.shape, (0, pr._BGE_M3_EMBEDDING_DIM))
        self.assertEqual(out.dtype, np.float64)

    def test_one_dim_response_is_reshaped_to_two_dim(self) -> None:
        flat = np.ones(pr._BGE_M3_EMBEDDING_DIM, dtype=np.float32)
        normalised = np.full((1, pr._BGE_M3_EMBEDDING_DIM), 0.5, dtype=np.float32)
        with (
            patch(
                "apps.pipeline.services.embeddings._encode_batch_via_provider",
                return_value=flat,
            ),
            patch("apps.pipeline.services.embeddings._get_batch_size", return_value=8),
            patch(
                "apps.pipeline.services.embeddings._l2_normalize",
                return_value=normalised,
            ) as norm,
        ):
            out = pr._encode_passage_batch(["one"], MagicMock())

        passed_to_normalize = norm.call_args.args[0]
        self.assertEqual(passed_to_normalize.shape, (1, pr._BGE_M3_EMBEDDING_DIM))
        self.assertIs(out, normalised)


class PersistPassageRowsTests(SimpleTestCase):
    def test_upserts_one_row_per_index_and_returns_vectors(self) -> None:
        content_item = MagicMock(name="content_item")
        passages = [_make_passage(0, "A", 3), _make_passage(1, "B", 4)]
        normalised = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float64)
        diff = pr._PassageDiffResult(
            embed_indices=[0, 1], embed_texts=["A", "B"], opq_indices=[]
        )
        resources = _make_resources(signature="sig-9")

        with patch("apps.content.models.PassageEmbedding") as model:
            vectors = pr._persist_passage_rows(
                content_item=content_item,
                passages=passages,
                normalised=normalised,
                diff=diff,
                resources=resources,
                hashes=["h0", "h1"],
                target_window=200,
            )

        self.assertEqual(model.objects.update_or_create.call_count, 2)
        self.assertEqual(set(vectors.keys()), {0, 1})
        self.assertEqual(vectors[0].tolist(), [0.1, 0.2])

    def test_no_pending_indices_yields_empty_dict(self) -> None:
        content_item = MagicMock(name="content_item")
        diff = pr._PassageDiffResult([], [], [])

        with patch("apps.content.models.PassageEmbedding") as model:
            vectors = pr._persist_passage_rows(
                content_item=content_item,
                passages=[],
                normalised=np.zeros((0, 2)),
                diff=diff,
                resources=_make_resources(),
                hashes=[],
                target_window=200,
            )

        self.assertEqual(vectors, {})
        model.objects.update_or_create.assert_not_called()


class EncodeAndPersistOpqTests(SimpleTestCase):
    def test_no_codebook_short_circuits(self) -> None:
        diff = pr._PassageDiffResult([], [], [0, 1])
        with patch("apps.content.models.PassageEmbedding") as model:
            pr._encode_and_persist_opq(
                content_item=MagicMock(),
                diff=diff,
                vectors_for_opq={},
                existing={},
                resources=_make_resources(codebook=None),
            )
        model.objects.filter.assert_not_called()

    def test_no_pending_indices_short_circuits(self) -> None:
        codebook = SimpleNamespace(corpus_signature="v1")
        diff = pr._PassageDiffResult([], [], [])
        with patch("apps.content.models.PassageEmbedding") as model:
            pr._encode_and_persist_opq(
                content_item=MagicMock(),
                diff=diff,
                vectors_for_opq={},
                existing={},
                resources=_make_resources(codebook=codebook),
            )
        model.objects.filter.assert_not_called()


class DeleteStalePassageRowsTests(SimpleTestCase):
    def test_skips_when_no_stale_indices(self) -> None:
        existing = {0: object(), 1: object()}
        with patch("apps.content.models.PassageEmbedding") as model:
            pr._delete_stale_passage_rows(MagicMock(), existing, current_count=2)
        model.objects.filter.assert_not_called()

    def test_deletes_indices_at_or_above_current_count(self) -> None:
        existing = {0: object(), 1: object(), 5: object(), 7: object()}
        with patch("apps.content.models.PassageEmbedding") as model:
            pr._delete_stale_passage_rows(MagicMock(), existing, current_count=3)

        model.objects.filter.assert_called_once()
        kwargs = model.objects.filter.call_args.kwargs
        self.assertEqual(sorted(kwargs["passage_index__in"]), [5, 7])


class LoadExistingPassageRowsTests(SimpleTestCase):
    def test_keys_returned_dict_by_passage_index(self) -> None:
        rows = [
            SimpleNamespace(passage_index=0),
            SimpleNamespace(passage_index=2),
            SimpleNamespace(passage_index=5),
        ]
        fake_qs = MagicMock()
        fake_qs.__iter__ = lambda self: iter(rows)

        with patch("apps.content.models.PassageEmbedding") as model:
            model.objects.filter.return_value = fake_qs
            out = pr._load_existing_passage_rows(MagicMock())

        self.assertEqual(set(out.keys()), {0, 2, 5})


class LoadEmbeddingResourcesTests(SimpleTestCase):
    def test_returns_codebook_when_one_is_active(self) -> None:
        cb = SimpleNamespace(corpus_signature="opq-2026-05")
        fake_filter = MagicMock()
        fake_filter.first.return_value = cb

        with (
            patch("apps.content.models.OPQCodebook") as codebook_model,
            patch(
                "apps.pipeline.services.embeddings._get_model_name",
                return_value="bge-m3",
            ),
            patch(
                "apps.pipeline.services.embeddings._load_model",
                return_value="model-handle",
            ),
            patch(
                "apps.pipeline.services.embeddings.get_current_embedding_signature",
                return_value="sig-7",
            ),
        ):
            codebook_model.objects.filter.return_value = fake_filter
            res = pr._load_embedding_resources()

        self.assertEqual(res.signature, "sig-7")
        self.assertIs(res.codebook, cb)
        self.assertEqual(res.opq_version, "opq-2026-05")

    def test_returns_empty_opq_version_when_no_codebook(self) -> None:
        fake_filter = MagicMock()
        fake_filter.first.return_value = None

        with (
            patch("apps.content.models.OPQCodebook") as codebook_model,
            patch(
                "apps.pipeline.services.embeddings._get_model_name",
                return_value="bge-m3",
            ),
            patch(
                "apps.pipeline.services.embeddings._load_model",
                return_value="model-handle",
            ),
            patch(
                "apps.pipeline.services.embeddings.get_current_embedding_signature",
                return_value="sig-7",
            ),
        ):
            codebook_model.objects.filter.return_value = fake_filter
            res = pr._load_embedding_resources()

        self.assertIsNone(res.codebook)
        self.assertEqual(res.opq_version, "")


class ConstantsTests(SimpleTestCase):
    def test_bge_m3_dim_is_documented_value(self) -> None:
        self.assertEqual(pr._BGE_M3_EMBEDDING_DIM, 1024)

    def test_overlap_sentences_in_recommended_range(self) -> None:
        self.assertGreaterEqual(pr._PASSAGE_OVERLAP_SENTENCES, 1)
        self.assertLessEqual(pr._PASSAGE_OVERLAP_SENTENCES, 5)
