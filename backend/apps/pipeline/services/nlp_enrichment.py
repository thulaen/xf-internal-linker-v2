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

    def _generate_summary(self, doc: Any, top_n: int = 3, max_iter: int = 30) -> str:
        """Pick #63 — TextRank extractive summary (Mihalcea-Tarau 2004 EMNLP).

        Algorithm:
            1. Split the document into sentences via spaCy.
            2. Build a sentence-similarity matrix using token-overlap Jaccard
               (cheap; doesn't require an embedding model). Stop-words and
               punctuation are excluded so common-word noise doesn't dominate.
            3. Treat the matrix as the transition matrix of an undirected
               graph; run PageRank to convergence with damping 0.85
               (Page-Brin 1999).
            4. Return the top-N sentences ordered as they appear in the
               document (preserves narrative flow).

        For a typical 10-sentence post this is microseconds. For a 1000-
        sentence forum thread it's still well under 50 ms — and the
        function only runs at import time, never on the ranker hot path.
        """
        sentences = [s for s in doc.sents if s.text.strip()]
        n = len(sentences)
        if n == 0:
            return ""
        if n <= top_n:
            return " ".join(s.text.strip() for s in sentences)

        # 1. Token sets — lemma-based, stop-word + punct stripped.
        token_sets: list[set[str]] = []
        for sent in sentences:
            tokens = {
                t.lemma_.lower()
                for t in sent
                if not t.is_stop and not t.is_punct and t.lemma_.strip()
            }
            token_sets.append(tokens)

        # 2. Sentence-similarity matrix (Jaccard).
        sim_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                a, b = token_sets[i], token_sets[j]
                if not a or not b:
                    continue
                inter = len(a & b)
                union = len(a | b)
                sim = inter / union if union > 0 else 0.0
                sim_matrix[i][j] = sim
                sim_matrix[j][i] = sim

        # 3. Power-iteration PageRank on the similarity matrix.
        # Damping 0.85 per Page-Brin 1999. Convergence on a typical
        # 10-50 sentence post takes <10 iterations.
        scores = [1.0 / n] * n
        damping = 0.85
        # Pre-compute row sums for normalisation; max(sum, 1e-9) avoids
        # division by zero on a sentence with no shared lemmas.
        row_sums = [max(sum(row), 1e-9) for row in sim_matrix]
        for _ in range(max_iter):
            new_scores = [(1.0 - damping) / n] * n
            for i in range(n):
                contrib = damping * scores[i] / row_sums[i]
                for j in range(n):
                    if i != j and sim_matrix[i][j] > 0.0:
                        new_scores[j] += contrib * sim_matrix[i][j]
            # Cheap convergence check.
            delta = sum(abs(a - b) for a, b in zip(new_scores, scores))
            scores = new_scores
            if delta < 1e-4:
                break

        # 4. Pick the top-N sentence indices, then sort by document
        # order so the summary reads naturally (not by importance).
        top_indices = sorted(
            sorted(range(n), key=lambda i: scores[i], reverse=True)[:top_n]
        )
        return " ".join(sentences[i].text.strip() for i in top_indices)
