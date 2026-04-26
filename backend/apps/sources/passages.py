"""Passage-level segmentation for long documents.

Reference: Callan, James P. (1994). "Passage-level evidence in
document retrieval." *Proceedings of the 17th ACM SIGIR Conference*,
pp. 302-310.

Callan's core insight: long documents are often a collection of
topically distinct passages; computing similarity against the
best-matching passage instead of a whole-document average is
substantially more precise. The cheapest variant (and the one he
concluded was "surprisingly effective") is fixed-window token
chunking with a small overlap between neighbours so passage
boundaries don't cut query-relevant phrases in half.

This module implements exactly that. Complementary to
:mod:`apps.pipeline.services.sentence_splitter` — the sentence
splitter produces human-readable units, while this module produces
retrieval-friendly, fixed-size windows keyed off whitespace
tokenisation. Callers pick whichever unit their pipeline wants.

Design rules:

- **Whitespace tokenisation.** We split on Python's default whitespace
  so the function has no locale/language dependency. Downstream
  ranking code still uses its own tokeniser; this one only needs to
  be good enough to produce stable window boundaries.
- **Deterministic output.** Same input → same windows. Tested via a
  round-trip that checks total token count and the start/end offsets.
- **No hidden heuristics.** Punctuation, sentence ends, and paragraph
  breaks are ignored — Callan's 1994 paper found that fixed windows
  performed within noise of smarter boundary heuristics while being
  much simpler.

If the caller wants sentence-aligned passages they can pass the
sentence splitter's output into :func:`segment_from_sentences` which
preserves sentence boundaries while still enforcing an approximate
window size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


#: Default window size in whitespace tokens. Callan 1994 §5 reports
#: 150-300 as the sweet spot across TREC collections; we pick the
#: lower end because BGE-M3 has a sequence limit and shorter windows
#: give more granular scoring. Callers can override.
DEFAULT_WINDOW_TOKENS: int = 150

#: Default overlap between neighbouring windows, in tokens. A ~20 %
#: overlap prevents query-relevant phrases from being chopped in half
#: at a boundary. Increase if your documents are heavily redundant.
DEFAULT_OVERLAP_TOKENS: int = 30


@dataclass(frozen=True)
class Passage:
    """One fixed-window slice of a source document."""

    index: int  # 0-based position in the list returned
    text: str  # raw passage text with whitespace preserved
    token_start: int  # inclusive
    token_end: int  # exclusive
    token_count: int  # end - start


# ── Token-window segmentation ────────────────────────────────────────


def segment_by_tokens(
    text: str,
    *,
    window_tokens: int = DEFAULT_WINDOW_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Passage]:
    """Split *text* into fixed-width token windows with overlap.

    Whitespace-tokenises the input, slides a window of
    ``window_tokens`` across it stepping by
    ``window_tokens - overlap_tokens``, and materialises each window
    as a :class:`Passage` with the original whitespace between tokens
    preserved.

    Short inputs (token count <= window_tokens) return a single
    passage spanning the whole text.
    """
    _guard_window_params(window_tokens, overlap_tokens)
    if not text:
        return []

    tokens_with_spans = list(_tokens_with_offsets(text))
    token_count = len(tokens_with_spans)
    if token_count == 0:
        return []
    if token_count <= window_tokens:
        # Whole-doc passage — overlap math would produce duplicates.
        start_offset = tokens_with_spans[0][1]
        end_offset = tokens_with_spans[-1][2]
        return [
            Passage(
                index=0,
                text=text[start_offset:end_offset],
                token_start=0,
                token_end=token_count,
                token_count=token_count,
            )
        ]

    stride = window_tokens - overlap_tokens
    passages: list[Passage] = []
    idx = 0
    start = 0
    while start < token_count:
        end = min(start + window_tokens, token_count)
        start_offset = tokens_with_spans[start][1]
        end_offset = tokens_with_spans[end - 1][2]
        passages.append(
            Passage(
                index=idx,
                text=text[start_offset:end_offset],
                token_start=start,
                token_end=end,
                token_count=end - start,
            )
        )
        idx += 1
        if end == token_count:
            break
        start += stride
    return passages


# ── Sentence-aligned segmentation ────────────────────────────────────


def segment_from_sentences(
    sentences: Iterable[str],
    *,
    target_window_tokens: int = DEFAULT_WINDOW_TOKENS,
    overlap_sentences: int = 1,
) -> list[Passage]:
    """Group *sentences* into passages aiming for ~``target_window_tokens`` tokens.

    Sentence boundaries are preserved — a passage is always a
    concatenation of whole sentences. Useful when the downstream
    display wants human-readable cuts (snippet preview on the
    review page, say) but the retrieval layer still benefits from
    ~passage-sized chunks.

    The *overlap_sentences* knob controls how many trailing sentences
    are shared between neighbouring passages. 1 is enough to keep
    queries that straddle a boundary findable; 0 turns off overlap.
    """
    if target_window_tokens <= 0:
        raise ValueError("target_window_tokens must be > 0")
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences must be >= 0")

    sentences_list = [s for s in sentences if s and s.strip()]
    if not sentences_list:
        return []

    passages: list[Passage] = []
    buffer: list[str] = []
    buffer_tokens = 0
    buffer_start_global_token = 0
    running_global_token = 0
    passage_idx = 0

    def flush(end_global_token: int) -> None:
        nonlocal passage_idx
        if not buffer:
            return
        passage_text = " ".join(buffer)
        passages.append(
            Passage(
                index=passage_idx,
                text=passage_text,
                token_start=buffer_start_global_token,
                token_end=end_global_token,
                token_count=end_global_token - buffer_start_global_token,
            )
        )
        passage_idx += 1

    for sentence in sentences_list:
        n_tokens = len(_whitespace_split(sentence))
        # If the buffer is already at/over target and the new sentence
        # would only push us further, flush first (unless buffer empty).
        if buffer and buffer_tokens + n_tokens > target_window_tokens:
            flush(running_global_token)
            if overlap_sentences > 0 and len(buffer) > overlap_sentences:
                tail = buffer[-overlap_sentences:]
                buffer = list(tail)
                buffer_tokens = sum(len(_whitespace_split(s)) for s in tail)
                buffer_start_global_token = running_global_token - buffer_tokens
            else:
                buffer = []
                buffer_tokens = 0
                buffer_start_global_token = running_global_token
        buffer.append(sentence)
        buffer_tokens += n_tokens
        running_global_token += n_tokens

    if buffer:
        flush(running_global_token)
    return passages


# ── Internals ────────────────────────────────────────────────────────


_WHITESPACE_SPLIT_RE = re.compile(r"\S+")


def _whitespace_split(text: str) -> list[str]:
    """Plain whitespace tokeniser — matches str.split() but with no copy."""
    return _WHITESPACE_SPLIT_RE.findall(text)


def _tokens_with_offsets(text: str) -> Iterable[tuple[str, int, int]]:
    """Yield (token, start_offset, end_offset) for every whitespace-bounded run."""
    for match in _WHITESPACE_SPLIT_RE.finditer(text):
        yield match.group(0), match.start(), match.end()


def _guard_window_params(window_tokens: int, overlap_tokens: int) -> None:
    if window_tokens <= 0:
        raise ValueError("window_tokens must be > 0")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be >= 0")
    if overlap_tokens >= window_tokens:
        raise ValueError("overlap_tokens must be < window_tokens")
