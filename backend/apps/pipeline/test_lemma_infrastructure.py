"""Smoke tests for Lemmatization Infrastructure (Slice 11)."""

import pytest
from django.db import transaction
from apps.content.models import ContentItem, Post, Sentence, Token
from apps.pipeline.services.nlp_enrichment import NLPEnricher
from apps.pipeline.tasks_import_helpers import _persist_content_body

@pytest.mark.django_db
def test_nlp_enricher_token_output():
    """Verify that NLPEnricher returns the expected granular token data."""
    enricher = NLPEnricher()
    text = "The quick brown foxes are jumping over the lazy dogs."
    metadata, char_ngram_vector, token_data = enricher.enrich(text)
    
    assert len(token_data) > 0
    # Check for specific lemmatization
    foxes_token = next((t for t in token_data if t["text"].lower() == "foxes"), None)
    assert foxes_token is not None
    assert foxes_token["lemma"] == "fox"
    
    jumping_token = next((t for t in token_data if t["text"].lower() == "jumping"), None)
    assert jumping_token is not None
    assert jumping_token["lemma"] == "jump"

@pytest.mark.django_db
def test_token_persistence():
    """Verify that Token records are correctly persisted during import."""
    content_item = ContentItem.objects.create(
        content_id=123,
        content_type="thread",
        title="Test Thread"
    )
    
    clean_text = "The cats are running. The dogs were sleeping."
    raw_body = "[URL='http://example.com']The cats are running.[/URL] The dogs were sleeping."
    
    # Simulate the persistence call
    _persist_content_body(
        content_item=content_item,
        raw_body=raw_body,
        clean_text=clean_text,
        new_hash="fake-hash-123",
        first_post_id=456
    )
    
    # Check Sentences
    sentences = Sentence.objects.filter(content_item=content_item).order_by('position')
    assert sentences.count() == 2
    
    # Check Tokens for the first sentence
    sent1 = sentences[0]
    tokens1 = Token.objects.filter(sentence=sent1).order_by('start_char')
    assert tokens1.count() > 0
    
    # Verify lemma collapse for "cats" -> "cat" and "running" -> "run"
    cats_lemma = tokens1.filter(text__iexact="cats").first().lemma
    assert cats_lemma == "cat"
    
    running_lemma = tokens1.filter(text__iexact="running").first().lemma
    assert running_lemma == "run"
    
    # Check Tokens for the second sentence "The dogs were sleeping."
    sent2 = sentences[1]
    tokens2 = Token.objects.filter(sentence=sent2).order_by('start_char')
    dogs_lemma = tokens2.filter(text__iexact="dogs").first().lemma
    assert dogs_lemma == "dog"
    
    sleeping_lemma = tokens2.filter(text__iexact="sleeping").first().lemma
    assert sleeping_lemma == "sleep"

@pytest.mark.django_db
def test_token_offsets_relative_to_sentence():
    """Verify that Token character offsets are relative to the sentence, not the whole post."""
    content_item = ContentItem.objects.create(
        content_id=789,
        content_type="thread",
        title="Offset Test"
    )
    
    # "The dogs" starts at index 37 in the whole text.
    clean_text = "The cats sit on the mat for a while. The dogs bark at the moon loudly."
    
    _persist_content_body(
        content_item=content_item,
        raw_body=clean_text,
        clean_text=clean_text,
        new_hash="fake-hash-789",
        first_post_id=999
    )
    
    sent2 = Sentence.objects.get(content_item=content_item, position=1)
    assert sent2.text == "The dogs bark at the moon loudly."
    
    dogs_token = Token.objects.get(sentence=sent2, text="dogs")
    # In "The dogs bark at the moon loudly.", "dogs" starts at index 4.
    assert dogs_token.start_char == 4
    assert dogs_token.end_char == 8
