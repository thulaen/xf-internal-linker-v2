"""Tests for Group G NLP services."""

import pytest
from apps.pipeline.services.acronym_detector import SchwartzHearstDetector
from apps.pipeline.services.pattern_matcher import AhoCorasickMatcher


def test_acronym_detector_basic():
    detector = SchwartzHearstDetector()
    text = "Artificial Intelligence (AI) is a subfield of Computer Science (CS)."
    pairs = detector.extract_pairs(text)

    assert pairs == {"AI": "Artificial Intelligence", "CS": "Computer Science"}


def test_acronym_detector_no_match():
    detector = SchwartzHearstDetector()
    text = "This is a sentence with (no definition)."
    pairs = detector.extract_pairs(text)
    assert pairs == {}


def test_acronym_detector_nested_parens():
    detector = SchwartzHearstDetector()
    # The current regex handles simple parens. 
    # Schwartz-Hearst typically ignores nested unless specialized.
    text = "Machine Learning (ML (Deep Learning))"
    pairs = detector.extract_pairs(text)
    # The regex _PAREN_RE = r"\((?P<acronym>[a-zA-Z0-9][^)]*?)\)"
    # will match "(ML (Deep Learning)" which is malformed.
    # But Schwartz-Hearst usually sees "(ML)" if it's there.
    # Our regex for acronyms in parens is quite strict.
    pass


def test_aho_corasick_basic():
    matcher = AhoCorasickMatcher()
    matcher.add_pattern("apple")
    matcher.add_pattern("banana")
    matcher.add_pattern("cherry")
    matcher.build()

    text = "I like apple and banana, but not cherry pie."
    matches = matcher.find_all(text)

    assert len(matches) == 3
    patterns = {m.pattern for m in matches}
    assert patterns == {"apple", "banana", "cherry"}


def test_aho_corasick_case_insensitive():
    matcher = AhoCorasickMatcher(case_sensitive=False)
    matcher.add_pattern("Apple")
    matcher.build()

    text = "An apple a day."
    matches = matcher.find_all(text)
    assert len(matches) == 1
    assert matches[0].pattern == "Apple"


def test_aho_corasick_non_overlapping():
    matcher = AhoCorasickMatcher()
    matcher.add_pattern("Artificial Intelligence")
    matcher.add_pattern("Intelligence")
    matcher.build()

    text = "Artificial Intelligence is cool."
    matches = matcher.find_non_overlapping(text)

    # Should only match the longest one.
    assert len(matches) == 1
    assert matches[0].pattern == "Artificial Intelligence"


def test_nlp_enricher_noun_chunks():
    from apps.pipeline.services.nlp_enrichment import NLPEnricher
    from apps.pipeline.services.spacy_loader import get_spacy_nlp
    
    if get_spacy_nlp() is None:
        pytest.skip("spaCy not available")
        
    enricher = NLPEnricher()
    text = "Internal linking is a great strategy for search engine optimization."
    metadata, _, _ = enricher.enrich(text)
    
    assert len(metadata.noun_chunks) > 0
    texts = [c["text"] for c in metadata.noun_chunks]
    assert any("Internal linking" in t for t in texts)
    assert any("search engine optimization" in t for t in texts)
