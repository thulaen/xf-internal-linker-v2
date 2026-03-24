"""Pure-Python anchor extraction for winning host sentences."""

from __future__ import annotations

from dataclasses import dataclass

from .ranker import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE


@dataclass(frozen=True, slots=True)
class AnchorExtraction:
    """Anchor phrase plus raw character offsets in the host sentence."""

    anchor_phrase: str | None
    anchor_start: int | None
    anchor_end: int | None
    anchor_confidence: str


@dataclass(frozen=True, slots=True)
class _TokenSpan:
    normalized: str
    start: int
    end: int


def extract_anchor(
    host_sentence_text: str,
    destination_title: str,
) -> AnchorExtraction:
    """Extract the best title-based anchor phrase from a host sentence.

    Matching is exact, case-insensitive, stopword-filtered, and uses
    contiguous token windows over the filtered token streams.
    """
    host_tokens = _tokenize_with_offsets(host_sentence_text)
    title_tokens = _tokenize_with_offsets(destination_title)

    if not host_tokens or not title_tokens:
        return AnchorExtraction(None, None, None, "none")

    title_norms = [token.normalized for token in title_tokens]
    host_norms = [token.normalized for token in host_tokens]

    max_window = min(len(title_norms), len(host_norms))
    for window_size in range(max_window, 0, -1):
        title_ngrams = _build_title_ngram_set(title_norms, window_size)
        if not title_ngrams:
            continue

        for host_start_idx in range(0, len(host_norms) - window_size + 1):
            host_ngram = tuple(host_norms[host_start_idx:host_start_idx + window_size])
            if host_ngram not in title_ngrams:
                continue

            first_token = host_tokens[host_start_idx]
            last_token = host_tokens[host_start_idx + window_size - 1]
            phrase = host_sentence_text[first_token.start:last_token.end]
            confidence = _confidence_for_match(host_ngram)
            if confidence == "none":
                continue

            return AnchorExtraction(
                anchor_phrase=phrase,
                anchor_start=first_token.start,
                anchor_end=last_token.end,
                anchor_confidence=confidence,
            )

    return AnchorExtraction(None, None, None, "none")


def _tokenize_with_offsets(text: str) -> list[_TokenSpan]:
    spans: list[_TokenSpan] = []
    for match in TOKEN_RE.finditer(text):
        normalized = match.group(0).lower()
        if normalized in STANDARD_ENGLISH_STOPWORDS:
            continue
        spans.append(
            _TokenSpan(
                normalized=normalized,
                start=match.start(),
                end=match.end(),
            )
        )
    return spans


def _build_title_ngram_set(
    title_norms: list[str],
    window_size: int,
) -> set[tuple[str, ...]]:
    if window_size <= 0 or window_size > len(title_norms):
        return set()

    if window_size == 1:
        return {
            (token,)
            for token in title_norms
            if len(token) >= 5
        }

    return {
        tuple(title_norms[start_idx:start_idx + window_size])
        for start_idx in range(0, len(title_norms) - window_size + 1)
    }


def _confidence_for_match(match_tokens: tuple[str, ...]) -> str:
    if len(match_tokens) >= 2:
        return "strong"
    if len(match_tokens) == 1 and len(match_tokens[0]) >= 5:
        return "weak"
    return "none"
