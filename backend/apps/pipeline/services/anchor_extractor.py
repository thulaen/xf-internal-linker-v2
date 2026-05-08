"""Pure-Python anchor extraction for winning host sentences."""

from __future__ import annotations

from dataclasses import dataclass

from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE
from .pattern_matcher import AhoCorasickMatcher


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

    matcher = AhoCorasickMatcher(case_sensitive=False)
    _SEP = "\u0000"

    # Build patterns for all possible title n-grams
    max_title_window = len(title_norms)
    for window_size in range(max_title_window, 0, -1):
        for start_idx in range(len(title_norms) - window_size + 1):
            ngram = title_norms[start_idx : start_idx + window_size]
            if window_size == 1 and len(ngram[0]) < 5:
                continue
            matcher.add_pattern(_SEP.join(ngram), window_size)

    matcher.build()

    # Scan host sentence for matches, preferring longest match first
    for window_size in range(len(host_norms), 0, -1):
        for host_start_idx in range(len(host_norms) - window_size + 1):
            host_ngram = host_norms[host_start_idx : host_start_idx + window_size]
            match_pattern = _SEP.join(host_ngram)
            matches = matcher.find_all(match_pattern)

            # We only care if the entire window matches a title n-gram
            if any(m.pattern == match_pattern for m in matches):
                first_token = host_tokens[host_start_idx]
                last_token = host_tokens[host_start_idx + window_size - 1]
                phrase = host_sentence_text[first_token.start : last_token.end]
                confidence = _confidence_for_match(tuple(host_ngram))
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


def _confidence_for_match(match_tokens: tuple[str, ...]) -> str:
    if len(match_tokens) >= 2:
        return "strong"
    if len(match_tokens) == 1 and len(match_tokens[0]) >= 5:
        return "weak"
    return "none"
