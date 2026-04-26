"""Phase 6.1 — VADER (#22) + PySBD (#15) + YAKE! (#17) wrapper tests.

The three wrappers all follow the same lazy-import + cold-start-safe
contract. Tests are split across three test classes; each class tests
the cold-start path (always works) and the real-call path (gated on
``unittest.skipUnless(HAS_<DEP>, ...)`` so they pass either way).
"""

from __future__ import annotations

import unittest

from django.test import SimpleTestCase

from apps.sources import pysbd_segmenter, vader_sentiment, yake_keywords


class VaderSentimentTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(vader_sentiment.is_available(), bool)

    def test_empty_text_returns_neutral(self) -> None:
        result = vader_sentiment.score("")
        self.assertIs(result, vader_sentiment.NEUTRAL)
        self.assertTrue(result.is_neutral)

    def test_neutral_singleton_shape(self) -> None:
        n = vader_sentiment.NEUTRAL
        self.assertEqual(n.compound, 0.0)
        self.assertEqual(n.positive, 0.0)
        self.assertEqual(n.negative, 0.0)
        self.assertEqual(n.neutral, 1.0)

    @unittest.skipUnless(vader_sentiment.HAS_VADER, "vaderSentiment not installed")
    def test_positive_text_has_positive_compound(self) -> None:
        result = vader_sentiment.score("This is a wonderful, amazing, fantastic day!")
        self.assertGreater(result.compound, 0.5)
        self.assertFalse(result.is_neutral)

    def test_cold_start_when_dep_missing_still_returns_neutral(self) -> None:
        """Documents the documented cold-start behaviour."""
        if not vader_sentiment.HAS_VADER:
            self.assertIs(vader_sentiment.score("anything"), vader_sentiment.NEUTRAL)
        else:
            self.skipTest("VADER is installed — cold-start test n/a")


class PysbdSegmenterTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(pysbd_segmenter.is_available(), bool)

    def test_empty_text_returns_empty_list(self) -> None:
        self.assertEqual(pysbd_segmenter.split(""), [])
        self.assertEqual(pysbd_segmenter.split("   "), [])

    def test_split_all_passes_through(self) -> None:
        result = pysbd_segmenter.split_all(["", "Hello.", "  "])
        self.assertEqual(len(result), 3)
        # First and third are empty; middle is one sentence either way.
        self.assertEqual(result[0], [])
        self.assertEqual(result[2], [])
        self.assertEqual(result[1], ["Hello."])

    def test_fallback_works_when_pysbd_missing(self) -> None:
        """Even without pysbd, the regex fallback splits on terminators."""
        text = "First sentence. Second sentence! Third sentence?"
        result = pysbd_segmenter.split(text)
        self.assertEqual(len(result), 3)

    @unittest.skipUnless(pysbd_segmenter.HAS_PYSBD, "pysbd not installed")
    def test_pysbd_handles_abbreviations_better_than_fallback(self) -> None:
        """Real PySBD doesn't split on Dr. ; the regex fallback does."""
        text = "I called Dr. Smith yesterday. He was busy."
        result = pysbd_segmenter.split(text)
        # PySBD should produce 2 sentences, regex fallback 3.
        self.assertEqual(len(result), 2)


class YakeKeywordsTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(yake_keywords.is_available(), bool)

    def test_empty_text_returns_empty_list(self) -> None:
        self.assertEqual(yake_keywords.extract(""), [])
        self.assertEqual(yake_keywords.extract("   "), [])

    def test_cold_start_when_yake_missing_returns_empty(self) -> None:
        if not yake_keywords.HAS_YAKE:
            self.assertEqual(
                yake_keywords.extract("Plenty of words here in this corpus"),
                [],
            )
        else:
            self.skipTest("YAKE is installed — cold-start test n/a")

    @unittest.skipUnless(yake_keywords.HAS_YAKE, "yake not installed")
    def test_extracts_repeated_phrase(self) -> None:
        text = (
            "Reciprocal rank fusion is a popular ensembling technique. "
            "Reciprocal rank fusion combines multiple rankers without "
            "tuning. The reciprocal rank fusion paper appeared at SIGIR."
        )
        hits = yake_keywords.extract(text, top_k=5)
        self.assertGreater(len(hits), 0)
        # The repeated phrase should appear in the top-K.
        keywords_lower = {hit.keyword.lower() for hit in hits}
        # "reciprocal rank fusion" appears 3x — should make the cut.
        # Match either the trigram or its tokens.
        self.assertTrue(
            any("reciprocal" in kw for kw in keywords_lower),
            f"expected 'reciprocal' in extracted keywords, got {keywords_lower}",
        )
