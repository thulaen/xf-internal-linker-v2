"""VADER sentiment scoring — pick #22.

Reference
---------
Hutto, C. J. & Gilbert, E. (2014). "VADER: A Parsimonious Rule-Based
Model for Sentiment Analysis of Social Media Text." *Proceedings of
the 8th International Conference on Weblogs and Social Media (ICWSM)*.

Wraps the ``vaderSentiment`` PyPI package so the rest of the pipeline
can ask for the polarity of a sentence without re-implementing the
7,500-token sentiment lexicon.

Why a thin wrapper?
- Single import boundary so swapping the underlying library (e.g. to
  TextBlob or to a transformer-based scorer) is one file edit, not
  a repo-wide grep.
- Lazy import (the ``vaderSentiment`` package isn't a hard dep).
  ``HAS_VADER`` mirrors the ``HAS_FAISS`` pattern used elsewhere so
  callers can branch cleanly.
- Cold-start safe: ``score(text)`` returns a neutral
  :class:`SentimentResult` when VADER isn't installed; consumers don't
  need to special-case the missing-dep path.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from vaderSentiment.vaderSentiment import (
        SentimentIntensityAnalyzer as _Analyzer,
    )

    HAS_VADER = True
except ImportError:  # pragma: no cover — depends on pip env
    _Analyzer = None  # type: ignore[assignment]
    HAS_VADER = False


@dataclass(frozen=True)
class SentimentResult:
    """One sentence's sentiment scores.

    Mirrors the four-value return of VADER's ``polarity_scores`` so
    consumers don't need to know the library's dict keys.
    """

    positive: float
    negative: float
    neutral: float
    compound: float  # -1..+1, Hutto-Gilbert's headline score

    @property
    def is_neutral(self) -> bool:
        """True when ``|compound| < 0.05`` — VADER's own neutrality cutoff."""
        return abs(self.compound) < 0.05


#: Returned when VADER isn't installed or the input text is empty.
#: Same shape as a real VADER result so consumers can compare without
#: ``is None`` checks first.
NEUTRAL = SentimentResult(positive=0.0, negative=0.0, neutral=1.0, compound=0.0)


_ANALYZER_SINGLETON = None


def _analyzer():
    """Return a process-wide :class:`SentimentIntensityAnalyzer`.

    The analyzer loads its 7.5K-entry lexicon at construction time;
    sharing one instance across calls is the correct pattern.
    """
    global _ANALYZER_SINGLETON
    if _ANALYZER_SINGLETON is None and HAS_VADER:
        _ANALYZER_SINGLETON = _Analyzer()
    return _ANALYZER_SINGLETON


def is_available() -> bool:
    """True when the ``vaderSentiment`` package can be used."""
    return HAS_VADER


def score(text: str) -> SentimentResult:
    """Return the four polarity scores for *text*.

    Empty input or missing pip dep → :data:`NEUTRAL` (caller does not
    need to special-case anything). Real-data ready: when the
    ``vaderSentiment`` package is installed, every call wires through
    automatically.
    """
    if not text or not HAS_VADER:
        return NEUTRAL
    raw = _analyzer().polarity_scores(text)
    return SentimentResult(
        positive=float(raw["pos"]),
        negative=float(raw["neg"]),
        neutral=float(raw["neu"]),
        compound=float(raw["compound"]),
    )
