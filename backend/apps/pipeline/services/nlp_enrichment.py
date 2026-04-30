"""NLP enrichment services for Group G (Harmonious-12).

Integrates lemmatization, noun-chunk extraction, and acronym detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .spacy_loader import get_spacy_nlp
from .acronym_detector import SchwartzHearstDetector


@dataclass(frozen=True, slots=True)
class NLPMetadata:
    """Bag of NLP features for a piece of text."""

    lemmas: list[str]
    noun_chunks: list[dict[str, Any]] # text, start, end
    acronyms: dict[str, str]
    # Pick #57 — Lexical Richness
    lexical_richness: dict[str, float]
    # Pick #60 — MinHash sketch (128 integers)
    minhash_sketch: list[int]
    # Pick #61 — Phonetic keys
    phonetic_keys: list[str]
    # Pick #63 — TextRank summary
    summary: str


class NLPEnricher:
    """High-level service to enrich text with NLP metadata."""

    def __init__(self):
        self.acronym_detector = SchwartzHearstDetector()

    def enrich(self, text: str, doc: Any | None = None) -> tuple[NLPMetadata, list[float] | None, list[dict[str, Any]]]:
        """Extract NLP metadata from text using spaCy and supplementary libraries.
        
        Returns a tuple of (NLPMetadata, char_ngram_vector, token_data).
        """
        from datasketch import MinHash
        from metaphone import doublemetaphone
        from sklearn.feature_extraction.text import HashingVectorizer

        nlp = get_spacy_nlp()
        
        lemmas = []
        noun_chunks = []
        tokens = []
        
        if doc is None and nlp is not None:
            doc = nlp(text)

        if doc is not None:
            # Pick #54 — Lemmatization
            lemmas = [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]
            
            # Pick #55 — Noun-chunks
            for chunk in doc.noun_chunks:
                noun_chunks.append({
                    "text": chunk.text,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                })
            
            tokens = [token.text.lower() for token in doc if not token.is_punct]

        # Pick #53 — Acronym Detection
        acronyms = self.acronym_detector.extract_pairs(text)
        
        # Pick #57 — Lexical Richness
        ttr = 0.0
        hapax_ratio = 0.0
        if tokens:
            unique_tokens = set(tokens)
            ttr = len(unique_tokens) / len(tokens)
            counts = {t: tokens.count(t) for t in unique_tokens}
            hapax_count = sum(1 for t, c in counts.items() if c == 1)
            hapax_ratio = hapax_count / len(tokens)
        
        lexical_richness = {"ttr": ttr, "hapax_ratio": hapax_ratio}

        # Pick #60 — MinHash (128 hashes)
        mh = MinHash(num_perm=128)
        for t in tokens:
            mh.update(t.encode("utf8"))
        minhash_sketch = mh.hashvalues.tolist()

        # Pick #61 — Phonetic keys (Double Metaphone)
        phonetic_keys = []
        # Encode title/noun-chunks
        # Only use chunk texts for encoding
        chunk_texts = [c["text"] for c in noun_chunks]
        words_to_encode = set(chunk_texts[:5]) # limit to top 5 chunks
        for word in words_to_encode:
            p1, p2 = doublemetaphone(word)
            if p1:
                phonetic_keys.append(p1)
            if p2:
                phonetic_keys.append(p2)
        phonetic_keys = list(set(phonetic_keys))

        # Pick #58 — Char n-gram Hashed TF-IDF (256-dim)
        vectorizer = HashingVectorizer(n_features=256, analyzer="char", ngram_range=(3, 5))
        char_ngram_vector = vectorizer.transform([text]).toarray()[0].tolist()

        # Pick #63 — TextRank summary (simplified extractive)
        summary = self._generate_summary(doc) if doc else ""

        token_data = []
        if doc is not None:
            for token in doc:
                token_data.append(
                    {
                        "text": token.text,
                        "lemma": token.lemma_,
                        "pos": token.pos_,
                        "is_stop": token.is_stop,
                        "start_char": token.idx,
                        "end_char": token.idx + len(token.text),
                    }
                )

        metadata = NLPMetadata(
            lemmas=lemmas,
            noun_chunks=noun_chunks,
            acronyms=acronyms,
            lexical_richness=lexical_richness,
            minhash_sketch=minhash_sketch,
            phonetic_keys=phonetic_keys,
            summary=summary,
        )

        return metadata, char_ngram_vector, token_data

    def _generate_summary(self, doc: Any) -> str:
        """Simple extractive summary based on sentence position and length for now.
        
        TextRank implementation with PageRank is pending in a separate service.
        """
        sentences = list(doc.sents)
        if not sentences:
            return ""
        # Return first 2 sentences as a placeholder summary
        return " ".join([s.text for s in sentences[:2]])
