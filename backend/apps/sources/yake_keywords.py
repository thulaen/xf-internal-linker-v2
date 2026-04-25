"""YAKE! unsupervised keyword extraction — pick #17.

Reference
---------
Campos, R., Mangaravite, V., Pasquali, A., Jorge, A., Nunes, C., &
Jatowt, A. (2020). "YAKE! Keyword Extraction from Single Documents
Using Multiple Local Features." *Information Sciences*, 509, 257-289.

YAKE! is an unsupervised, language-agnostic keyword extractor that
ranks candidate phrases by a combination of casing, position,
frequency, sentence relatedness, and term-different-from-stopword
features. No training corpus required — it scores keywords from a
single document.

Wraps the ``yake`` PyPI package. Cold-start safe: when ``yake``
isn't installed, returns an empty list so callers can branch on
``len(keywords)`` without checking ``HAS_YAKE`` first.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import yake as _yake

    HAS_YAKE = True
except ImportError:  # pragma: no cover — depends on pip env
    _yake = None  # type: ignore[assignment]
    HAS_YAKE = False


@dataclass(frozen=True)
class KeywordHit:
    """One extracted keyword with its YAKE! score (lower = more relevant)."""

    keyword: str
    score: float


#: YAKE!'s recommended defaults from the paper §3.5 — n=3 captures
#: tri-grams, deduplication threshold 0.9 keeps Levenshtein-similar
#: phrases out of the top-K, top=20 covers the typical "5-20 keywords
#: per doc" use case.
DEFAULT_NGRAM_MAX: int = 3
DEFAULT_DEDUP_THRESHOLD: float = 0.9
DEFAULT_TOP_K: int = 20


def is_available() -> bool:
    """True when the ``yake`` package is importable."""
    return HAS_YAKE


def extract(
    text: str,
    *,
    language: str = "en",
    ngram_max: int = DEFAULT_NGRAM_MAX,
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> list[KeywordHit]:
    """Extract the top-K keywords from *text*.

    Empty input → ``[]``. Missing pip dep → ``[]``. Real-data ready:
    install ``yake`` and every call wires through automatically.

    YAKE! constructs a per-document extractor on each call (the
    library doesn't expose a stateful corpus model — the score is
    computed entirely from local features), so we don't cache an
    instance.
    """
    if not text or not text.strip() or not HAS_YAKE:
        return []
    extractor = _yake.KeywordExtractor(
        lan=language,
        n=ngram_max,
        dedupLim=dedup_threshold,
        top=top_k,
    )
    raw = extractor.extract_keywords(text)
    return [KeywordHit(keyword=str(kw), score=float(score)) for kw, score in raw]
