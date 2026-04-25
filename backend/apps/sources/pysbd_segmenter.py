"""PySBD sentence segmentation — pick #15.

Reference
---------
Sadvilkar, N. & Neumann, M. (2020). "PySBD: Pragmatic Sentence
Boundary Disambiguation." *Proceedings of the 2020 Conference on
Natural Language Processing Demonstrations* (ACL).

PySBD is a rule-based sentence boundary detector that handles edge
cases (abbreviations, decimals, ellipses, quotes, list items) better
than naïve ``re.split`` or NLTK's Punkt — those are particularly weak
on forum prose with mixed punctuation.

Wraps the ``pysbd`` PyPI package. Cold-start safe: when ``pysbd``
isn't installed, falls through to a basic regex splitter so callers
still get *some* sentence boundaries to work with — better than
crashing.
"""

from __future__ import annotations

import re
from typing import Iterable

try:
    from pysbd import Segmenter as _Segmenter

    HAS_PYSBD = True
except ImportError:  # pragma: no cover — depends on pip env
    _Segmenter = None  # type: ignore[assignment]
    HAS_PYSBD = False


#: Fallback regex used when PySBD isn't available. Matches the same
#: sentence-terminator characters PySBD recognises but without the
#: edge-case handling — abbreviations like "Dr." get split. The
#: fallback is documented as worse on purpose so production runs the
#: real thing.
_FALLBACK_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_SEGMENTER_SINGLETON = None


def _segmenter():
    """Return a process-wide PySBD :class:`Segmenter`.

    PySBD's ``Segmenter`` is light to construct but allocates rule
    tables on every init. Cache one per process.
    """
    global _SEGMENTER_SINGLETON
    if _SEGMENTER_SINGLETON is None and HAS_PYSBD:
        _SEGMENTER_SINGLETON = _Segmenter(language="en", clean=False)
    return _SEGMENTER_SINGLETON


def is_available() -> bool:
    """True when ``pysbd`` is importable."""
    return HAS_PYSBD


def split(text: str) -> list[str]:
    """Return *text* split into sentences.

    Empty or whitespace-only input → ``[]``. Missing PySBD →
    regex-based fallback that's worse on edge cases but still
    produces usable output. Real-data ready: install ``pysbd`` and
    the call automatically upgrades.

    Honours the ``pysbd_segmenter.enabled`` AppSetting toggle (cached
    via :mod:`apps.core.runtime_flags`); when the operator flips the
    toggle off, this falls back to the regex splitter even if PySBD
    is installed. Empty input still returns ``[]``.
    """
    if not text or not text.strip():
        return []
    from apps.core.runtime_flags import is_enabled

    if HAS_PYSBD and is_enabled("pysbd_segmenter.enabled", default=True):
        return [s for s in _segmenter().segment(text) if s.strip()]
    # Fallback — naive regex split.
    return [s.strip() for s in _FALLBACK_SPLIT_RE.split(text) if s.strip()]


def split_all(texts: Iterable[str]) -> list[list[str]]:
    """Sentence-split each element of *texts*."""
    return [split(t) for t in texts]
