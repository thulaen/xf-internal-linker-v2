"""Tests for Group G NLP services.

Originally written for pytest; converted to Django ``SimpleTestCase`` so
it runs under ``manage.py test``. None of these tests need a database.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.acronym_detector import SchwartzHearstDetector
from apps.pipeline.services.pattern_matcher import AhoCorasickMatcher


class AcronymDetectorTests(SimpleTestCase):
    """Schwartz-Hearst acronym + expansion extraction."""

    def test_basic(self):
        detector = SchwartzHearstDetector()
        text = "Artificial Intelligence (AI) is a subfield of Computer " "Science (CS)."
        pairs = detector.extract_pairs(text)
        self.assertEqual(
            pairs,
            {"AI": "Artificial Intelligence", "CS": "Computer Science"},
        )

    def test_no_match(self):
        detector = SchwartzHearstDetector()
        pairs = detector.extract_pairs("This is a sentence with (no definition).")
        self.assertEqual(pairs, {})

    def test_nested_parens_does_not_crash(self):
        # Schwartz-Hearst ignores malformed nested parens; verify no
        # raise — the original test had no assertion either.
        detector = SchwartzHearstDetector()
        detector.extract_pairs("Machine Learning (ML (Deep Learning))")


class AhoCorasickMatcherTests(SimpleTestCase):
    """Aho-Corasick pattern matching."""

    def test_basic(self):
        matcher = AhoCorasickMatcher()
        for pattern in ("apple", "banana", "cherry"):
            matcher.add_pattern(pattern)
        matcher.build()
        matches = matcher.find_all("I like apple and banana, but not cherry pie.")
        self.assertEqual(len(matches), 3)
        self.assertEqual(
            {m.pattern for m in matches},
            {"apple", "banana", "cherry"},
        )

    def test_case_insensitive(self):
        matcher = AhoCorasickMatcher(case_sensitive=False)
        matcher.add_pattern("Apple")
        matcher.build()
        matches = matcher.find_all("An apple a day.")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, "Apple")

    def test_non_overlapping_picks_longest(self):
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("Artificial Intelligence")
        matcher.add_pattern("Intelligence")
        matcher.build()
        matches = matcher.find_non_overlapping("Artificial Intelligence is cool.")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, "Artificial Intelligence")


class NLPEnricherNounChunksTests(SimpleTestCase):
    """spaCy-backed noun-chunk extraction (skipped when spaCy unavailable)."""

    def test_noun_chunks(self):
        from apps.pipeline.services.nlp_enrichment import NLPEnricher
        from apps.pipeline.services.spacy_loader import get_spacy_nlp

        if get_spacy_nlp() is None:
            self.skipTest("spaCy not available")

        enricher = NLPEnricher()
        metadata, _, _ = enricher.enrich(
            "Internal linking is a great strategy for search engine " "optimization."
        )
        self.assertGreater(len(metadata.noun_chunks), 0)
        texts = [c["text"] for c in metadata.noun_chunks]
        self.assertTrue(any("Internal linking" in t for t in texts))
        self.assertTrue(any("search engine optimization" in t for t in texts))
