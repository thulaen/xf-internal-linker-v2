"""Pick #55 — NLP enrichment + phrase matching benchmark smoke tests.

Originally written for pytest; converted to Django TestCase so it runs
under ``manage.py test`` (the project's only test runner).
"""

from __future__ import annotations

import time
from dataclasses import asdict

from django.test import TestCase

from apps.pipeline.services.nlp_enrichment import NLPEnricher
from apps.pipeline.services.phrase_matching import (
    PhraseMatchResult,
    evaluate_phrase_match,
)
from apps.pipeline.services.spacy_loader import get_spacy_nlp


class Pick55BenchTests(TestCase):
    """Lightweight benchmarks for the NLP enrichment + phrase-match path."""

    def setUp(self) -> None:
        self.enricher = NLPEnricher()

    def test_debug_spacy(self):
        nlp = get_spacy_nlp()
        if nlp is None:
            self.skipTest("spaCy not available")
        doc = nlp("Internal linking is great for SEO.")
        self.assertGreater(len(list(doc.noun_chunks)), 0)

    def test_noun_chunk_extraction_performance(self):
        text = "The quick brown fox jumps over the lazy dog. " * 50
        start = time.perf_counter()
        metadata, _, _ = self.enricher.enrich(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertIsNotNone(metadata.noun_chunks)
        self.assertGreater(len(metadata.noun_chunks), 0)
        self.assertLess(
            elapsed_ms,
            5000.0,
            f"NLP enrichment too slow: {elapsed_ms:.2f}ms",
        )

    def test_phrase_matching_with_noun_chunks(self):
        host_text = "Internal linking is great for SEO."
        metadata, _, _ = self.enricher.enrich(host_text)
        result = evaluate_phrase_match(
            host_sentence_text=host_text,
            destination_title="SEO Guide",
            destination_distilled_text=(
                "Internal linking is the practice of linking to other "
                "pages on the same website."
            ),
            host_nlp_metadata=asdict(metadata),
        )
        self.assertIsInstance(result, PhraseMatchResult)
        self.assertIn("alternative_anchors", result.phrase_match_diagnostics)
        alts = result.phrase_match_diagnostics["alternative_anchors"]
        self.assertGreater(len(alts), 0)

    def test_phrase_matching_performance(self):
        host_text = "The quick brown fox jumps over the lazy dog. " * 10
        metadata, _, _ = self.enricher.enrich(host_text)
        meta_dict = asdict(metadata)
        start = time.perf_counter()
        for _ in range(100):
            evaluate_phrase_match(
                host_sentence_text=host_text,
                destination_title="Animals",
                destination_distilled_text="A quick brown fox and a lazy dog.",
                host_nlp_metadata=meta_dict,
            )
        avg_ms = ((time.perf_counter() - start) / 100) * 1000
        self.assertLess(
            avg_ms,
            50.0,
            f"phrase match avg too slow: {avg_ms:.2f}ms",
        )
