"""Sentence splitting for cleaned post text.

Backend priority (best → worst), each falling through cleanly when
its dependency or model is missing:

1. **PySBD #15** (Sadvilkar & Neumann 2020 ACL Demos) — rule-based
   pragmatic boundary disambiguation; handles abbreviations,
   decimals, ellipses, quoted dialogue, and list items robustly.
   Toggle: ``pysbd_segmenter.enabled``.
2. **spaCy en_core_web_sm** — neural sentence segmenter, accurate
   on standard prose. Used when PySBD isn't installed (or the
   operator turned its toggle off). Doc is also returned for
   downstream entity / POS reuse.
3. **Regex fallback** — naïve split on sentence-terminator
   punctuation. Last-resort for installs without spaCy or PySBD.

PySBD doesn't return character offsets directly, so this module
recomputes them by scanning the original text in order — the same
approach the spaCy and regex paths use.

Reference
---------
- Sadvilkar, N. & Neumann, M. (2020). "PySBD: Pragmatic Sentence
  Boundary Disambiguation." ACL 2020 Demonstrations.
- Honnibal, M. & Montani, I. (2017). "spaCy 2: Natural language
  understanding with Bloom embeddings, convolutional neural
  networks and incremental parsing."
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .spacy_loader import get_spacy_nlp, is_spacy_available


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    """A sentence with its position and character offsets in the source text."""

    text: str
    position: int
    start_char: int
    end_char: int


_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])" r"|(?:\n\s*\n)")

_MIN_SENT_LEN = 15


def _pysbd_active() -> bool:
    """True when PySBD is installed AND its operator toggle is on."""
    try:
        from apps.sources import pysbd_segmenter
        from apps.core.runtime_flags import is_enabled

        if not pysbd_segmenter.is_available():
            return False
        return is_enabled("pysbd_segmenter.enabled", default=True)
    except Exception:
        return False


def _pysbd_split_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Run PySBD and recompute character offsets in the source text.

    PySBD's ``segment`` returns sentence strings as substrings of the
    input (we construct the segmenter with ``clean=False``), so each
    sentence appears in order and does not overlap. We scan the
    source from the end of the previous sentence to find each one's
    offset.
    """
    from apps.sources import pysbd_segmenter

    sentences = pysbd_segmenter.split(text)
    offsets: list[tuple[str, int, int]] = []
    cursor = 0
    for raw in sentences:
        stripped = raw.strip()
        if not stripped:
            continue
        idx = text.find(stripped, cursor)
        if idx < 0:
            # PySBD returned a sentence we can't locate (cleaning
            # mismatch); skip rather than poison the pipeline.
            continue
        offsets.append((stripped, idx, idx + len(stripped)))
        cursor = idx + len(stripped)
    return offsets


def split_sentences(text: str) -> list[str]:
    """Split cleaned text into sentences.

    Returns a list of non-trivial sentence strings.
    """
    return [span.text for span in split_sentence_spans(text)]


def split_sentence_spans(text: str) -> list[SentenceSpan]:
    """Split cleaned text into sentence spans with character offsets.

    Thin wrapper over :func:`split_sentence_spans_with_doc` that
    discards the underlying spaCy ``Doc``. Use the wider function
    when you also want entity / POS / dep info — the parse cost is
    the same either way.
    """
    spans, _doc = split_sentence_spans_with_doc(text)
    return spans


def split_sentence_spans_with_doc(text: str):
    """Split cleaned text and also return the underlying spaCy ``Doc``.

    Returns ``(spans, doc)``. The ``doc`` is ``None`` when spaCy
    isn't available (regex fallback) or when ``text`` is empty.
    Callers that need further NLP (entity ranking, POS, deps) reuse
    the same Doc so the text is parsed exactly once per import.

    The return type is intentionally untyped (no ``Doc`` import
    here) so this module stays importable in minimal containers
    without spaCy. The ``_Doc`` protocol in
    :mod:`apps.sources.entity_salience` is wide enough to type-check
    against this output.
    """
    if not text or not text.strip():
        return [], None

    # Backend priority for sentence boundaries: PySBD first (best on
    # forum prose), then spaCy, then regex.
    #
    # We ALWAYS try to parse with spaCy in parallel when it's
    # available, because downstream consumers (entity ranking, POS,
    # deps in tasks_import_helpers._persist_content_body) need the
    # spaCy ``Doc``. If PySBD provides better sentence boundaries,
    # we use them — but spaCy still parses the same text once for
    # its NLP outputs.
    doc = None
    raw_spans: list[tuple[str, int, int]] = []

    nlp = get_spacy_nlp()
    if nlp is not None:
        # Single parse — used for downstream NLP reuse regardless of
        # which sentence-boundary backend is the spans source.
        doc = nlp(text)

    if _pysbd_active():
        raw_spans = _pysbd_split_with_offsets(text)

    if not raw_spans:
        if doc is not None:
            raw_spans = [
                (sent.text.strip(), sent.start_char, sent.end_char)
                for sent in doc.sents
            ]
        else:
            raw_spans = _regex_split_with_offsets(text)

    spans: list[SentenceSpan] = []
    position = 0
    for raw_text, start, end in raw_spans:
        if len(raw_text) >= _MIN_SENT_LEN:
            spans.append(
                SentenceSpan(
                    text=raw_text,
                    position=position,
                    start_char=start,
                    end_char=end,
                )
            )
            position += 1
    return spans, doc


def _regex_split_with_offsets(text: str) -> list[tuple[str, int, int]]:
    parts: list[tuple[str, int, int]] = []
    last_end = 0
    for match in _SENT_RE.finditer(text):
        segment = text[last_end : match.start()]
        stripped = segment.strip()
        if stripped:
            offset = last_end + segment.index(stripped)
            parts.append((stripped, offset, offset + len(stripped)))
        last_end = match.end()
    tail = text[last_end:]
    stripped = tail.strip()
    if stripped:
        offset = last_end + tail.index(stripped)
        parts.append((stripped, offset, offset + len(stripped)))
    return parts


def get_backend() -> str:
    """Return which sentence-splitting backend is active.

    Tracks the priority chain in :func:`split_sentence_spans_with_doc`:
    PySBD when its dep + toggle are both active, then spaCy, then
    regex. Used by diagnostics + the Settings UI to surface which
    splitter the operator's ranker is actually using.
    """
    if _pysbd_active():
        return "pysbd"
    return "spacy" if is_spacy_available() else "regex"
