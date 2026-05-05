"""Tests for the pure-function helpers extracted from pipeline/services/embeddings.py.

These helpers replaced ~600 lines of inlined branching across the 8 long
``_*`` and ``generate_*_embeddings`` entrypoints. Each is independently
testable in ``SimpleTestCase`` (no DB) so a future tweak to a coefficient
or threshold shows up here before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.pipeline.services.embeddings import (
    _build_content_item_text_inputs,
    _build_sentence_text_inputs,
    _extract_existing_quality_gate_inputs,
    _PROVIDER_FALLBACK_REASON_CODES,
    _quality_gate_should_skip,
)


class BuildContentItemTextInputsTests(SimpleTestCase):
    """``_build_content_item_text_inputs`` builds the (pks, texts, hashes) triple."""

    def test_clean_text_preferred_over_distilled(self):
        items = [(1, "Title", "Long clean body", "Distilled summary")]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(pks, [1])
        self.assertEqual(texts[0], "Title\n\nLong clean body")
        self.assertEqual(len(hashes), 1)

    def test_distilled_fallback_when_clean_empty(self):
        items = [(1, "Title", "", "Distilled summary")]
        _, texts, _ = _build_content_item_text_inputs(items)
        self.assertEqual(texts[0], "Title\n\nDistilled summary")

    def test_title_only_when_no_body(self):
        items = [(1, "Title", "", "")]
        _, texts, _ = _build_content_item_text_inputs(items)
        self.assertEqual(texts[0], "Title")

    def test_skips_completely_empty_rows(self):
        items = [(1, "", "", ""), (2, "Real Title", "Real body", "")]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(pks, [2])
        self.assertEqual(len(texts), 1)
        self.assertEqual(len(hashes), 1)

    def test_lengths_align(self):
        # The (pks, texts, hashes) lists MUST stay length-aligned for
        # _flush_embeddings_slice's zip(strict=True) to not raise.
        items = [(i, f"T{i}", f"B{i}", "") for i in range(5)]
        pks, texts, hashes = _build_content_item_text_inputs(items)
        self.assertEqual(len(pks), len(texts))
        self.assertEqual(len(texts), len(hashes))


class BuildSentenceTextInputsTests(SimpleTestCase):
    """``_build_sentence_text_inputs`` skips empty/whitespace sentences."""

    def test_strips_whitespace(self):
        sentences = [(1, "  hello  "), (2, "world")]
        pks, texts = _build_sentence_text_inputs(sentences)
        self.assertEqual(texts, ["hello", "world"])
        self.assertEqual(pks, [1, 2])

    def test_skips_empty_text(self):
        sentences = [(1, ""), (2, "real")]
        pks, texts = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])
        self.assertEqual(texts, ["real"])

    def test_skips_whitespace_only(self):
        sentences = [(1, "   "), (2, "real")]
        pks, _ = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])

    def test_skips_none_text(self):
        sentences = [(1, None), (2, "real")]
        pks, _ = _build_sentence_text_inputs(sentences)
        self.assertEqual(pks, [2])


class ProviderFallbackReasonCodesTests(SimpleTestCase):
    """The fallback whitelist that ``_encode_via_provider_with_fallback`` honours."""

    def test_contains_all_recoverable_codes(self):
        # Per FR-234 these are the four codes that are safe to swap on.
        self.assertIn("auth", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("rate_limit", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("budget", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertIn("transient", _PROVIDER_FALLBACK_REASON_CODES)

    def test_does_not_contain_irrecoverable_codes(self):
        # provider_error / unknown / etc must propagate so the operator sees them.
        self.assertNotIn("provider_error", _PROVIDER_FALLBACK_REASON_CODES)
        self.assertNotIn("unknown", _PROVIDER_FALLBACK_REASON_CODES)


class QualityGateShouldSkipTests(SimpleTestCase):
    """``_quality_gate_should_skip`` checks model class + non-empty pks + signature."""

    def _model(self, name: str):
        m = mock.Mock()
        m.__name__ = name
        return m

    def test_non_content_item_skipped(self):
        self.assertTrue(_quality_gate_should_skip(
            model_class=self._model("Sentence"),
            pks_slice=[1, 2], embedding_signature="bge-m3-v1",
        ))

    def test_empty_pks_skipped(self):
        self.assertTrue(_quality_gate_should_skip(
            model_class=self._model("ContentItem"),
            pks_slice=[], embedding_signature="bge-m3-v1",
        ))

    def test_no_signature_skipped(self):
        self.assertTrue(_quality_gate_should_skip(
            model_class=self._model("ContentItem"),
            pks_slice=[1], embedding_signature=None,
        ))

    def test_all_satisfied_does_not_skip(self):
        self.assertFalse(_quality_gate_should_skip(
            model_class=self._model("ContentItem"),
            pks_slice=[1], embedding_signature="bge-m3-v1",
        ))


class ExtractExistingQualityGateInputsTests(SimpleTestCase):
    """``_extract_existing_quality_gate_inputs`` pulls (old_vec, old_sig, text) from a row."""

    def test_none_row_returns_defaults(self):
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(None, True)
        self.assertIsNone(old_vec)
        self.assertEqual(old_sig, "")
        self.assertIsNone(text)

    def test_row_without_embedding_returns_none_vec(self):
        row = {
            "embedding": None, "embedding_model_version": "bge-v1",
            "title": "T", "distilled_text": "D",
        }
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(row, True)
        self.assertIsNone(old_vec)
        self.assertEqual(old_sig, "bge-v1")
        self.assertEqual(text, "T\n\nD")

    def test_row_with_valid_embedding(self):
        row = {
            "embedding": [0.1, 0.2, 0.3], "embedding_model_version": "v1",
            "title": "Title", "distilled_text": "Body",
        }
        old_vec, old_sig, text = _extract_existing_quality_gate_inputs(row, True)
        self.assertIsNotNone(old_vec)
        self.assertEqual(old_vec.shape, (3,))
        self.assertEqual(old_sig, "v1")
        self.assertEqual(text, "Title\n\nBody")

    def test_no_signature_field(self):
        # When the model doesn't have embedding_model_version, sig should be "".
        row = {"embedding": None, "title": "T", "distilled_text": "D"}
        _, old_sig, _ = _extract_existing_quality_gate_inputs(row, False)
        self.assertEqual(old_sig, "")

    def test_corrupt_embedding_becomes_none(self):
        # asarray fails on a non-numeric value → fall back to None so the
        # gate accepts the new vector.
        row = {
            "embedding": ["not-a-number", "really"], "title": "T", "distilled_text": "D",
        }
        old_vec, _, _ = _extract_existing_quality_gate_inputs(row, False)
        self.assertIsNone(old_vec)
