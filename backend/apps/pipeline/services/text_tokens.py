"""Shared tokenization helpers used by pipeline scoring services."""

from __future__ import annotations

import re

try:
    from extensions import texttok

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
STANDARD_ENGLISH_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can't",
        "cannot",
        "could",
        "couldn't",
        "did",
        "didn't",
        "do",
        "does",
        "doesn't",
        "doing",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "hadn't",
        "has",
        "hasn't",
        "have",
        "haven't",
        "having",
        "he",
        "he'd",
        "he'll",
        "he's",
        "her",
        "here",
        "here's",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "how's",
        "i",
        "i'd",
        "i'll",
        "i'm",
        "i've",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "let's",
        "me",
        "more",
        "most",
        "mustn't",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "shan't",
        "she",
        "she'd",
        "she'll",
        "she's",
        "should",
        "shouldn't",
        "so",
        "some",
        "such",
        "than",
        "that",
        "that's",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "there's",
        "these",
        "they",
        "they'd",
        "they'll",
        "they're",
        "they've",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "wasn't",
        "we",
        "we'd",
        "we'll",
        "we're",
        "we've",
        "were",
        "weren't",
        "what",
        "what's",
        "when",
        "when's",
        "where",
        "where's",
        "which",
        "while",
        "who",
        "who's",
        "whom",
        "why",
        "why's",
        "with",
        "won't",
        "would",
        "wouldn't",
        "you",
        "you'd",
        "you'll",
        "you're",
        "you've",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


def _tokenize_text_py(text: str, stopwords: frozenset[str]) -> frozenset[str]:
    """Tokenize one text using the Python regex reference behavior."""
    tokens = {
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if token and token.lower() not in stopwords
    }
    return frozenset(tokens)


def tokenize_text_batch(
    texts: list[str],
    stopwords: frozenset[str],
) -> list[frozenset[str]]:
    """Tokenize many texts into deduplicated token sets."""
    return [_tokenize_text_py(text, stopwords) for text in texts]


def tokenize_text(text: str) -> frozenset[str]:
    """Tokenize text for set-style overlap scoring."""
    if HAS_CPP_EXT:
        return texttok.tokenize_text_batch([text or ""], STANDARD_ENGLISH_STOPWORDS)[0]
    return tokenize_text_batch([text], STANDARD_ENGLISH_STOPWORDS)[0]


def tokenize_text_stemmed(text: str) -> frozenset[str]:
    """Tokenize text **and** reduce each token to its Snowball stem (pick #21).

    Reuses :func:`tokenize_text` for the tokenisation pass — stopword
    list, lowercasing, and the C++ texttok extension when present —
    then maps each surviving token through
    :func:`apps.sources.snowball_stem.stem_token`. Returns a
    ``frozenset`` so callers can do set intersection / union the same
    way they do with :func:`tokenize_text`.

    Stemming collapses morphological variants (running, runs, run all
    map to ``run``), increasing recall on inflectional matches at the
    cost of slightly looser semantics. Consumers that opt in via the
    ``parse.stemmer.enabled`` setting pick this up; the default ranker
    pipeline uses the un-stemmed :func:`tokenize_text` and is
    behaviour-stable.

    Cold-start safe: when the ``snowballstemmer`` package is missing
    (minimal test container), :func:`stem_token` falls back to the
    identity function and this helper degrades to ``tokenize_text``.
    """
    # Local import — keeps text_tokens.py importable in containers
    # that don't ship the source layer.
    from apps.sources.snowball_stem import stem_token

    base = tokenize_text(text)
    if not base:
        return frozenset()
    return frozenset(stem_token(t) for t in base)
