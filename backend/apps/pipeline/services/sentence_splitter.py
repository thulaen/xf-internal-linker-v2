"""Sentence splitting for cleaned post text.

Uses spaCy en_core_web_sm when available, falls back to regex-based splitting.
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

    nlp = get_spacy_nlp()
    doc = None
    if nlp is not None:
        doc = nlp(text)
        raw_spans = [
            (sent.text.strip(), sent.start_char, sent.end_char) for sent in doc.sents
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
    """Return which sentence-splitting backend is active."""
    return "spacy" if is_spacy_available() else "regex"
