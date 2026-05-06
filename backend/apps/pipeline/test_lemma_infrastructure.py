"""Smoke tests for Lemmatization Infrastructure (Slice 11).

Originally written for pytest; converted to Django TestCase so it runs
under ``manage.py test``.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Sentence, Token
from apps.pipeline.services.nlp_enrichment import NLPEnricher
from apps.pipeline.tasks_import_helpers import _persist_content_body


class LemmaInfrastructureTests(TestCase):
    """Verify NLPEnricher token output and Token persistence end-to-end."""

    def test_nlp_enricher_token_output(self):
        enricher = NLPEnricher()
        text = "The quick brown foxes are jumping over the lazy dogs."
        _metadata, _char_ngram_vector, token_data = enricher.enrich(text)
        self.assertGreater(len(token_data), 0)
        foxes_token = next(
            (t for t in token_data if t["text"].lower() == "foxes"), None
        )
        self.assertIsNotNone(foxes_token)
        self.assertEqual(foxes_token["lemma"], "fox")
        jumping_token = next(
            (t for t in token_data if t["text"].lower() == "jumping"), None
        )
        self.assertIsNotNone(jumping_token)
        self.assertEqual(jumping_token["lemma"], "jump")

    def test_token_persistence(self):
        content_item = ContentItem.objects.create(
            content_id=123,
            content_type="thread",
            title="Test Thread",
        )
        clean_text = "The cats are running. The dogs were sleeping."
        raw_body = (
            "[URL='http://example.com']The cats are running.[/URL] "
            "The dogs were sleeping."
        )
        _persist_content_body(
            content_item=content_item,
            raw_body=raw_body,
            clean_text=clean_text,
            new_hash="fake-hash-123",
            first_post_id=456,
        )
        sentences = Sentence.objects.filter(
            content_item=content_item
        ).order_by("position")
        self.assertEqual(sentences.count(), 2)

        sent1 = sentences[0]
        tokens1 = Token.objects.filter(sentence=sent1).order_by("start_char")
        self.assertGreater(tokens1.count(), 0)
        self.assertEqual(
            tokens1.filter(text__iexact="cats").first().lemma, "cat"
        )
        self.assertEqual(
            tokens1.filter(text__iexact="running").first().lemma, "run"
        )

        sent2 = sentences[1]
        tokens2 = Token.objects.filter(sentence=sent2).order_by("start_char")
        self.assertEqual(
            tokens2.filter(text__iexact="dogs").first().lemma, "dog"
        )
        self.assertEqual(
            tokens2.filter(text__iexact="sleeping").first().lemma, "sleep"
        )

    def test_token_offsets_relative_to_sentence(self):
        content_item = ContentItem.objects.create(
            content_id=789,
            content_type="thread",
            title="Offset Test",
        )
        clean_text = (
            "The cats sit on the mat for a while. "
            "The dogs bark at the moon loudly."
        )
        _persist_content_body(
            content_item=content_item,
            raw_body=clean_text,
            clean_text=clean_text,
            new_hash="fake-hash-789",
            first_post_id=999,
        )
        sent2 = Sentence.objects.get(content_item=content_item, position=1)
        self.assertEqual(sent2.text, "The dogs bark at the moon loudly.")
        dogs_token = Token.objects.get(sentence=sent2, text="dogs")
        # In "The dogs bark at the moon loudly.", "dogs" starts at index 4.
        self.assertEqual(dogs_token.start_char, 4)
        self.assertEqual(dogs_token.end_char, 8)
