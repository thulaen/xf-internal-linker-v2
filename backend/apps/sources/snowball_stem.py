"""Pick #21 — Snowball / Porter2 stemmer wrapper.

Stemming reduces inflectional variants (``running``, ``ran``, ``runs``)
to a common base form (``run``) so two pieces of text that talk about
the same concept get matched even when their morphology differs. The
Snowball implementation of Martin Porter's revised stemming algorithm
(Porter 1980, refined as "Porter2" / "Snowball" in 2001) is the
canonical English stemmer used in IR research.

This module is a *thin* adapter on top of the upstream
``snowballstemmer`` package. The package is pure-Python and pulls in
zero transitive dependencies — chosen over NLTK's
``nltk.stem.SnowballStemmer`` so the production image doesn't have to
ship NLTK's tokeniser, corpus downloader, or other heavyweights.

Two public callables:

- :func:`stem_token(token, language)` — stem a single, already-tokenised
  word. Idempotent: re-stemming a stem returns the same string.
- :func:`stem_text(text, language)` — split on simple whitespace, stem
  each piece, return a list of stems.

Cold-start safe: if the underlying package isn't installed (e.g. a
test container without the dep), the helpers fall back to the
identity function and emit a single warning. No part of the ranker
crashes because stemming is unavailable.

The helper does **not** wire itself into the live ranker — that's a
separate slice. Once available, picks like #17 YAKE!,
``score_keyword``, and the ``rare_term_propagation`` matcher can opt
in to stemmed-token comparison.

Reference
---------
Porter, M.F. (1980). "An algorithm for suffix stripping."
*Program: electronic library and information systems* 14(3): 130-137.

Porter, M.F. & Boulton, R. (2001). "The Snowball string processing
language." Available at https://snowballstem.org/ .
"""

from __future__ import annotations

import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)


#: Default language for the stemmer. Snowball supports 25+ languages
#: but the rest of the repo is English-only today, so this is the
#: intentional starting point. Callers that want to stem other
#: languages pass ``language="french"`` etc. to either helper.
DEFAULT_LANGUAGE: str = "english"


#: Tokeniser used by :func:`stem_text`. Splits on runs of any
#: non-alphanumeric character so ``"running, ran!"`` → ``["running",
#: "ran"]``. Intentionally simple — callers that need a smarter
#: tokeniser (NER-aware, hyphen-preserving, etc.) should tokenise
#: themselves and call :func:`stem_token` per piece.
_TOKENISER = re.compile(r"[A-Za-z0-9]+")


def _identity(token: str) -> str:
    return token


def _build_stemmer(language: str) -> Callable[[str], str]:
    """Return a ``stem(token) -> stem`` callable for *language*.

    Falls back to the identity function (with a one-time warning) when
    the ``snowballstemmer`` package is unavailable in the runtime —
    keeps tests in minimal containers from crashing.
    """
    try:
        import snowballstemmer
    except ImportError:
        logger.warning(
            "snowballstemmer not installed — stemming returns identity. "
            "Add `snowballstemmer` to requirements.txt to enable."
        )
        return _identity

    try:
        impl = snowballstemmer.stemmer(language)
    except KeyError:
        logger.warning(
            "snowballstemmer: unknown language %r — falling back to identity",
            language,
        )
        return _identity

    def _stem(token: str) -> str:
        return impl.stemWord(token)

    return _stem


# Per-language cache so we build the stemmer once per process.
_STEMMER_CACHE: dict[str, Callable[[str], str]] = {}


def _get_stemmer(language: str) -> Callable[[str], str]:
    cached = _STEMMER_CACHE.get(language)
    if cached is None:
        cached = _build_stemmer(language)
        _STEMMER_CACHE[language] = cached
    return cached


def stem_token(token: str, *, language: str = DEFAULT_LANGUAGE) -> str:
    """Return the Snowball stem of a single token.

    Lower-cases the input first because Snowball's English rules are
    case-sensitive (``"Running"`` and ``"running"`` would otherwise
    yield different stems on some implementations). Empty strings pass
    through unchanged.
    """
    if not token:
        return token
    stemmer = _get_stemmer(language)
    return stemmer(token.lower())


def stem_text(text: str, *, language: str = DEFAULT_LANGUAGE) -> list[str]:
    """Tokenise *text* on simple alphanumeric runs and stem each piece.

    Returns an empty list for empty / None input. The tokeniser strips
    punctuation; callers that need to preserve it should tokenise
    themselves and call :func:`stem_token` per piece.

    Idempotent on already-stemmed text within a single language —
    re-applying does not over-stem.
    """
    if not text:
        return []
    stemmer = _get_stemmer(language)
    return [stemmer(match.group(0).lower()) for match in _TOKENISER.finditer(text)]


def is_available() -> bool:
    """True iff the underlying ``snowballstemmer`` package is importable.

    Useful for governance + diagnostics ("is stemming actually wired in
    this container?") without forcing callers to handle ImportError
    themselves.
    """
    try:
        import snowballstemmer  # noqa: F401
    except ImportError:
        return False
    return True
