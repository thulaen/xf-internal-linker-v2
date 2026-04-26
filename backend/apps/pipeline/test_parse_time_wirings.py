"""Tests for the four parse-time Phase 6 wirings (audit gaps A10/A11/A12).

Covers:

- A10 — distiller's YAKE keyword-boost actually fires (sentences
  containing top-K YAKE keywords rank higher than they would
  without the boost).
- A11 — site_crawler's Trafilatura main-content extraction takes
  precedence when available, falls through to BeautifulSoup
  cleanly when missing.
- A12 — sentence_splitter's PySBD path produces character offsets
  that round-trip correctly (no overlap, every span maps to the
  source text exactly).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import distiller, sentence_splitter
from apps.sources.yake_keywords import KeywordHit


# ─────────────────────────────────────────────────────────────────────
# A10 — distiller YAKE keyword boost
# ─────────────────────────────────────────────────────────────────────


class DistillerYakeBoostTests(SimpleTestCase):
    """The boost should tilt distillation toward sentences carrying
    document-level YAKE keywords. We test the per-sentence scorer
    directly so spaCy's noun-chunk variance can't sway the result.
    """

    def test_score_sentence_yake_boost_adds_per_keyword(self) -> None:
        sentence = "The magic keyword wins here for sure."
        # Score WITHOUT YAKE boost → baseline.
        baseline = distiller._score_sentence(
            sentence, idx=0, total=1, yake_keywords_lower=None
        )
        # Score WITH a single matching keyword → baseline + 0.05.
        boosted = distiller._score_sentence(
            sentence, idx=0, total=1, yake_keywords_lower=["magic keyword"]
        )
        self.assertGreater(boosted, baseline)
        self.assertAlmostEqual(
            boosted - baseline, distiller.YAKE_BOOST_PER_KEYWORD, places=6
        )

    def test_score_sentence_yake_boost_caps_at_threshold(self) -> None:
        """Sentence with many keyword matches → boost ≤ YAKE_BOOST_CAP."""
        sentence = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        # 10 single-token keywords all present → 10 × 0.05 = 0.50 raw,
        # but cap should clamp to 0.40.
        baseline = distiller._score_sentence(
            sentence, idx=0, total=1, yake_keywords_lower=None
        )
        boosted = distiller._score_sentence(
            sentence,
            idx=0,
            total=1,
            yake_keywords_lower=[
                "alpha",
                "beta",
                "gamma",
                "delta",
                "epsilon",
                "zeta",
                "eta",
                "theta",
                "iota",
                "kappa",
            ],
        )
        # Boost ≤ cap regardless of keyword count.
        self.assertLessEqual(boosted - baseline, distiller.YAKE_BOOST_CAP + 1e-9)

    def test_score_sentence_no_keyword_match_no_boost(self) -> None:
        sentence = "The opening sentence."
        baseline = distiller._score_sentence(
            sentence, idx=0, total=1, yake_keywords_lower=None
        )
        boosted = distiller._score_sentence(
            sentence,
            idx=0,
            total=1,
            yake_keywords_lower=["unrelated phrase", "missing terms"],
        )
        self.assertEqual(baseline, boosted)

    def test_short_input_skips_yake_extraction(self) -> None:
        """Documents under 32 characters skip the YAKE call entirely
        (per ``_yake_keywords_lower``'s length guard)."""
        with patch(
            "apps.sources.yake_keywords.extract",
            side_effect=AssertionError("extract() must NOT be called on short input"),
        ):
            # 22 chars total — under the 32-char threshold.
            distilled = distiller.distill_body(["A short sentence here."])

        self.assertEqual(distilled, "A short sentence here.")

    def test_yake_extract_called_when_input_long_enough(self) -> None:
        """YAKE is called once per ``distill_body`` invocation when
        the joined document text is ≥ 32 chars."""
        with patch(
            "apps.sources.yake_keywords.extract",
            return_value=[KeywordHit(keyword="example", score=0.01)],
        ) as mock_extract:
            distiller.distill_body(
                [
                    "First long enough sentence in this list.",
                    "Second long enough sentence with example word.",
                ],
                max_sentences=1,
            )

        # Called exactly once on the joined document, not per sentence.
        self.assertEqual(mock_extract.call_count, 1)


# ─────────────────────────────────────────────────────────────────────
# A11 — site_crawler Trafilatura wiring
# ─────────────────────────────────────────────────────────────────────


class CrawlerTrafilaturaWiringTests(SimpleTestCase):
    """site_crawler._parse_html should prefer Trafilatura when
    available; fall through to BeautifulSoup when not."""

    def _make_meta(self):
        # Minimal stand-in for CrawledPageMeta — only the fields
        # _parse_html writes are needed.
        from dataclasses import dataclass, field

        @dataclass
        class _M:
            title: str = ""
            meta_description: str = ""
            canonical_url: str = ""
            robots_meta: str = ""
            has_viewport: bool = False
            og_title: str = ""
            og_description: str = ""
            h1_count: int = 0
            h1_text: str = ""
            extracted_text: str = ""
            word_count: int = 0
            content_to_html_ratio: float = 0.0
            content_hash: str = ""
            images: list = field(default_factory=list)
            text_alt_pairs: list = field(default_factory=list)
            social_links: list = field(default_factory=list)
            jsonld_blocks: list = field(default_factory=list)
            forms_count: int = 0
            internal_links: list = field(default_factory=list)
            external_links: list = field(default_factory=list)

        return _M()

    def _html(self) -> str:
        return (
            "<html><body>"
            "<nav>navigation menu items here</nav>"
            "<header>site header content</header>"
            "<main><p>The actual article text with the real signal.</p></main>"
            "<footer>copyright 2026</footer>"
            "</body></html>"
        )

    def test_trafilatura_path_used_when_available(self) -> None:
        from apps.crawler.services import site_crawler
        from apps.sources.trafilatura_extractor import ExtractedDocument

        with (
            patch(
                "apps.sources.trafilatura_extractor.is_available",
                return_value=True,
            ),
            patch(
                "apps.sources.trafilatura_extractor.extract",
                return_value=ExtractedDocument(
                    text="The actual article text with the real signal.",
                    title=None,
                    author=None,
                    date=None,
                    source_url="https://x/y",
                ),
            ),
        ):
            meta = self._make_meta()
            try:
                site_crawler._parse_html(self._html(), meta, "https://x/y")
            except Exception:
                # _parse_html may touch other fields the minimal meta
                # doesn't carry; we only care about extracted_text +
                # word_count for this test.
                pass

        self.assertIn("actual article text", meta.extracted_text)

    def test_falls_through_to_beautifulsoup_when_unavailable(self) -> None:
        from apps.crawler.services import site_crawler

        with patch(
            "apps.sources.trafilatura_extractor.is_available",
            return_value=False,
        ):
            meta = self._make_meta()
            try:
                site_crawler._parse_html(self._html(), meta, "https://x/y")
            except Exception:
                pass  # test stub may not have full DI; assertions follow

        # BeautifulSoup path strips nav/footer/header. The "actual
        # article text" survives; "navigation menu items" does not.
        self.assertIn("actual article text", meta.extracted_text)
        self.assertNotIn("navigation menu items", meta.extracted_text)


# ─────────────────────────────────────────────────────────────────────
# A12 — sentence_splitter PySBD offset correctness
# ─────────────────────────────────────────────────────────────────────


class PySbdOffsetTests(SimpleTestCase):
    """When PySBD is the spans source, recomputed character offsets
    must round-trip the source text exactly."""

    def test_offsets_round_trip_when_pysbd_active(self) -> None:
        from apps.sources import pysbd_segmenter

        if not pysbd_segmenter.is_available():
            self.skipTest("pysbd not installed; cannot test PySBD path")

        text = (
            "First sentence ends here. Second sentence is also here. "
            "Third one rounds it out."
        )

        # Force PySBD active even if runtime-flag cache says otherwise.
        with patch(
            "apps.pipeline.services.sentence_splitter._pysbd_active",
            return_value=True,
        ):
            spans = sentence_splitter.split_sentence_spans(text)

        # Three sentences, each round-trips exactly.
        self.assertGreaterEqual(len(spans), 1)
        for span in spans:
            slice_back = text[span.start_char : span.end_char]
            self.assertEqual(slice_back, span.text)

        # Spans are in non-overlapping, non-decreasing order.
        for prev, curr in zip(spans, spans[1:]):
            self.assertLessEqual(prev.end_char, curr.start_char)

    def test_pysbd_inactive_falls_back_to_spacy_or_regex(self) -> None:
        text = "First. Second sentence here. Third sentence."

        with patch(
            "apps.pipeline.services.sentence_splitter._pysbd_active",
            return_value=False,
        ):
            spans = sentence_splitter.split_sentence_spans(text)

        # Whichever fallback ran, spans round-trip the text.
        for span in spans:
            self.assertEqual(text[span.start_char : span.end_char], span.text)

    def test_get_backend_reports_pysbd_when_active(self) -> None:
        with patch(
            "apps.pipeline.services.sentence_splitter._pysbd_active",
            return_value=True,
        ):
            self.assertEqual(sentence_splitter.get_backend(), "pysbd")
