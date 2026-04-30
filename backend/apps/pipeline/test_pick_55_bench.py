import time
import pytest
from apps.pipeline.services.nlp_enrichment import NLPEnricher
from apps.pipeline.services.phrase_matching import evaluate_phrase_match, PhraseMatchResult
from apps.pipeline.services.spacy_loader import get_spacy_nlp
from dataclasses import asdict

@pytest.fixture
def enricher():
    return NLPEnricher()

@pytest.mark.django_db
def test_debug_spacy():
    nlp = get_spacy_nlp()
    if nlp is None:
        pytest.skip("spaCy not available")
    
    text = "Internal linking is great for SEO."
    doc = nlp(text)
    print(f"\nText: {text}")
    print(f"Noun chunks: {[chunk.text for chunk in doc.noun_chunks]}")
    print(f"Pipeline: {nlp.pipe_names}")
    
    assert len(list(doc.noun_chunks)) > 0

@pytest.mark.django_db
def test_noun_chunk_extraction_performance(enricher):
    text = "The quick brown fox jumps over the lazy dog. " * 50
    
    start_time = time.perf_counter()
    metadata, _, _ = enricher.enrich(text)
    end_time = time.perf_counter()
    
    duration_ms = (end_time - start_time) * 1000
    print(f"\nNLP enrichment duration: {duration_ms:.2f}ms")
    
    assert metadata.noun_chunks is not None
    print(f"Metadata noun chunks count: {len(metadata.noun_chunks)}")
    assert len(metadata.noun_chunks) > 0
    
@pytest.mark.django_db
def test_phrase_matching_with_noun_chunks(enricher):
    host_text = "Internal linking is great for SEO."
    metadata, _, _ = enricher.enrich(host_text)
    
    result = evaluate_phrase_match(
        host_sentence_text=host_text,
        destination_title="SEO Guide",
        destination_distilled_text="Internal linking is the practice of linking to other pages on the same website.",
        host_nlp_metadata=asdict(metadata)
    )
    
    assert isinstance(result, PhraseMatchResult)
    assert "alternative_anchors" in result.phrase_match_diagnostics
    alts = result.phrase_match_diagnostics["alternative_anchors"]
    
    print(f"Alternative anchors count: {len(alts)}")
    for alt in alts:
        print(f"Alt: {alt}")
    
    assert len(alts) > 0

@pytest.mark.django_db
def test_phrase_matching_performance(enricher):
    host_text = "The quick brown fox jumps over the lazy dog. " * 10
    metadata, _, _ = enricher.enrich(host_text)
    
    meta_dict = asdict(metadata)
    
    start_time = time.perf_counter()
    for _ in range(100):
        evaluate_phrase_match(
            host_sentence_text=host_text,
            destination_title="Animals",
            destination_distilled_text="A quick brown fox and a lazy dog.",
            host_nlp_metadata=meta_dict
        )
    end_time = time.perf_counter()
    
    avg_duration_ms = ((end_time - start_time) / 100) * 1000
    print(f"\nAverage phrase matching duration: {avg_duration_ms:.2f}ms")
    
    assert avg_duration_ms < 5.0
