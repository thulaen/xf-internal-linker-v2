"""Text-normalisation helpers (Unicode Standard Annex #15).

Reference: Unicode Consortium (2023). *Unicode Standard Annex #15 —
Unicode Normalization Forms*. ``NFKC`` is the compatibility-composed
form: canonical-decomposition followed by canonical-composition plus
mapping of compatibility-equivalent sequences onto their simpler
counterparts.

Why this matters for the linker: two text fragments that look
identical to a human can carry different byte sequences (``"café"``
with a precomposed ``U+00E9`` vs. the same glyph as ``e`` +
combining acute ``U+0301``). Every downstream step — hashing,
embedding, matching, BM25 — will treat them as distinct unless the
text is normalised first.

This module is deliberately a thin wrapper around ``unicodedata`` so
the caller can't get the arguments wrong, and so we centralise the
choice of form (NFKC) in one place — changing it later is a one-line
edit here instead of a repo-wide grep.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable


#: The normalisation form we've standardised on. NFKC is the most
#: aggressive — it folds compatibility equivalents (fullwidth digits,
#: ligatures, superscripts, etc.) onto their canonical counterparts,
#: which is the right default for retrieval pipelines.
NORMALIZATION_FORM: str = "NFKC"


def nfkc(text: str) -> str:
    """Return the NFKC-normalised form of *text*.

    Passing ``None`` or the empty string returns the input unchanged —
    callers routinely hand in optional fields and we don't want to
    turn those into ``TypeError``.
    """
    if not text:
        return text
    return unicodedata.normalize(NORMALIZATION_FORM, text)


def nfkc_all(texts: Iterable[str]) -> list[str]:
    """Normalise every element of *texts*. Empty strings pass through."""
    return [nfkc(t) if t else t for t in texts]


def is_normalised(text: str) -> bool:
    """True when *text* is already in NFKC form (no-op expected)."""
    if not text:
        return True
    return unicodedata.is_normalized(NORMALIZATION_FORM, text)
