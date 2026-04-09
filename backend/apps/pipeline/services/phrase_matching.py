"""FR-008 phrase matching and anchor expansion."""

from __future__ import annotations

from dataclasses import dataclass
import re

try:
    from extensions import phrasematch

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE


MAX_PHRASE_TOKENS = 5
MAX_DESTINATION_PHRASES = 24
PARTIAL_MIN_TOKEN_OVERLAP = 2
PARTIAL_MIN_OVERLAP_RATIO = 0.60
MIN_SINGLE_TOKEN_CHARS = 5

_SEGMENT_SPLIT_RE = re.compile(r"(?:\r?\n+|(?<=[.!?])\s+)")


@dataclass(frozen=True, slots=True)
class PhraseMatchingSettings:
    """Operator-facing FR-008 settings."""

    ranking_weight: float = 0.0
    enable_anchor_expansion: bool = True
    enable_partial_matching: bool = True
    context_window_tokens: int = 8


@dataclass(frozen=True, slots=True)
class PhraseMatchResult:
    """Explainable phrase score plus chosen anchor span."""

    score_phrase_relevance: float
    score_phrase_component: float
    anchor_phrase: str | None
    anchor_start: int | None
    anchor_end: int | None
    anchor_confidence: str
    phrase_match_diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class _TokenSpan:
    normalized: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _PhraseOccurrence:
    tokens: tuple[str, ...]
    surface: str
    source_field: str
    source_rank: int
    segment_index: int
    start_index: int
    source_order: int


@dataclass(frozen=True, slots=True)
class _DestinationPhrase:
    tokens: tuple[str, ...]
    surface: str
    source_field: str
    source_rank: int
    source_order: int

    @property
    def token_count(self) -> int:
        return len(self.tokens)


@dataclass(frozen=True, slots=True)
class _HostSpan:
    start_index: int
    end_index: int
    tokens: tuple[str, ...]
    anchor_start: int
    anchor_end: int
    anchor_phrase: str

    @property
    def token_count(self) -> int:
        return len(self.tokens)


@dataclass(frozen=True, slots=True)
class _MatchCandidate:
    score_phrase_relevance: float
    anchor_phrase: str
    anchor_start: int
    anchor_end: int
    anchor_confidence: str
    phrase_match_state: str
    selected_match_type: str
    selected_phrase_source: str
    selected_token_count: int
    context_corroborating_hits: int
    is_exact: bool
    source_rank: int
    sentence_position: int

    @property
    def score_phrase_component(self) -> float:
        return score_phrase_relevance_component(self.score_phrase_relevance)

    def diagnostics(
        self, *, destination_phrase_count: int, context_window_tokens: int
    ) -> dict[str, object]:
        return {
            "score_phrase_relevance": round(self.score_phrase_relevance, 6),
            "phrase_match_state": self.phrase_match_state,
            "selected_anchor_text": self.anchor_phrase,
            "selected_anchor_start": self.anchor_start,
            "selected_anchor_end": self.anchor_end,
            "selected_match_type": self.selected_match_type,
            "selected_phrase_source": self.selected_phrase_source,
            "selected_token_count": self.selected_token_count,
            "context_window_tokens": context_window_tokens,
            "context_corroborating_hits": self.context_corroborating_hits,
            "destination_phrase_count": destination_phrase_count,
        }


def score_phrase_relevance_component(score_phrase_relevance: float) -> float:
    """Center the stored FR-008 score for additive ranking."""
    return max(0.0, min(1.0, 2.0 * (float(score_phrase_relevance) - 0.5)))


def evaluate_phrase_match(
    *,
    host_sentence_text: str,
    destination_title: str,
    destination_distilled_text: str,
    settings: PhraseMatchingSettings | None = None,
) -> PhraseMatchResult:
    """Return the FR-008 phrase score, diagnostics, and chosen anchor."""
    config = settings or PhraseMatchingSettings()
    try:
        return _evaluate_phrase_match(
            host_sentence_text=host_sentence_text,
            destination_title=destination_title,
            destination_distilled_text=destination_distilled_text,
            settings=config,
        )
    except Exception:
        fallback = _run_current_fallback(host_sentence_text, destination_title)
        if fallback.anchor_phrase:
            candidate = _build_fallback_candidate(fallback)
            return PhraseMatchResult(
                score_phrase_relevance=candidate.score_phrase_relevance,
                score_phrase_component=candidate.score_phrase_component,
                anchor_phrase=candidate.anchor_phrase,
                anchor_start=candidate.anchor_start,
                anchor_end=candidate.anchor_end,
                anchor_confidence=candidate.anchor_confidence,
                phrase_match_diagnostics=candidate.diagnostics(
                    destination_phrase_count=0,
                    context_window_tokens=config.context_window_tokens,
                ),
            )
        return _neutral_result(
            phrase_match_state="neutral_no_host_match",
            destination_phrase_count=0,
            context_window_tokens=config.context_window_tokens,
        )


def _evaluate_phrase_match(
    *,
    host_sentence_text: str,
    destination_title: str,
    destination_distilled_text: str,
    settings: PhraseMatchingSettings,
) -> PhraseMatchResult:
    destination_phrases = _build_destination_phrase_inventory(
        destination_title=destination_title,
        destination_distilled_text=destination_distilled_text,
    )
    destination_phrase_count = len(destination_phrases)
    if destination_phrase_count == 0:
        return _neutral_with_fallback(
            host_sentence_text=host_sentence_text,
            destination_title=destination_title,
            phrase_match_state="neutral_no_destination_phrases",
            destination_phrase_count=destination_phrase_count,
            context_window_tokens=settings.context_window_tokens,
        )

    if not settings.enable_anchor_expansion:
        return _neutral_with_fallback(
            host_sentence_text=host_sentence_text,
            destination_title=destination_title,
            phrase_match_state="neutral_no_host_match",
            destination_phrase_count=destination_phrase_count,
            context_window_tokens=settings.context_window_tokens,
        )

    host_tokens = _tokenize_with_offsets(host_sentence_text)
    if not host_tokens:
        return _neutral_with_fallback(
            host_sentence_text=host_sentence_text,
            destination_title=destination_title,
            phrase_match_state="neutral_no_host_match",
            destination_phrase_count=destination_phrase_count,
            context_window_tokens=settings.context_window_tokens,
        )

    host_spans = _build_host_spans(host_sentence_text, host_tokens)
    destination_token_set = {
        token for phrase in destination_phrases for token in phrase.tokens
    }

    best_exact: _MatchCandidate | None = None
    best_partial: _MatchCandidate | None = None
    partial_below_threshold = False

    for span in host_spans:
        for phrase in destination_phrases:
            if span.tokens == phrase.tokens:
                candidate = _build_match_candidate(
                    span=span,
                    phrase=phrase,
                    match_type="exact",
                    context_hits=_count_context_hits(
                        span=span,
                        host_tokens=host_tokens,
                        host_spans=host_spans,
                        destination_phrases=destination_phrases,
                        destination_token_set=destination_token_set,
                        context_window_tokens=settings.context_window_tokens,
                    ),
                )
                if best_exact is None or _match_sort_key(candidate) < _match_sort_key(
                    best_exact
                ):
                    best_exact = candidate
                continue

            if not settings.enable_partial_matching:
                continue

            overlap_len = _longest_contiguous_overlap(span.tokens, phrase.tokens)
            if overlap_len < PARTIAL_MIN_TOKEN_OVERLAP:
                continue
            overlap_ratio = overlap_len / min(len(span.tokens), len(phrase.tokens))
            context_hits = _count_context_hits(
                span=span,
                host_tokens=host_tokens,
                host_spans=host_spans,
                destination_phrases=destination_phrases,
                destination_token_set=destination_token_set,
                context_window_tokens=settings.context_window_tokens,
            )
            if overlap_ratio < PARTIAL_MIN_OVERLAP_RATIO or context_hits < 1:
                partial_below_threshold = True
                continue

            candidate = _build_match_candidate(
                span=span,
                phrase=phrase,
                match_type="partial",
                context_hits=context_hits,
            )
            if best_partial is None or _match_sort_key(candidate) < _match_sort_key(
                best_partial
            ):
                best_partial = candidate

    winner = best_exact or best_partial
    if winner is not None:
        return PhraseMatchResult(
            score_phrase_relevance=winner.score_phrase_relevance,
            score_phrase_component=winner.score_phrase_component,
            anchor_phrase=winner.anchor_phrase,
            anchor_start=winner.anchor_start,
            anchor_end=winner.anchor_end,
            anchor_confidence=winner.anchor_confidence,
            phrase_match_diagnostics=winner.diagnostics(
                destination_phrase_count=destination_phrase_count,
                context_window_tokens=settings.context_window_tokens,
            ),
        )

    neutral_state = (
        "neutral_partial_below_threshold"
        if partial_below_threshold
        else "neutral_no_host_match"
    )
    return _neutral_with_fallback(
        host_sentence_text=host_sentence_text,
        destination_title=destination_title,
        phrase_match_state=neutral_state,
        destination_phrase_count=destination_phrase_count,
        context_window_tokens=settings.context_window_tokens,
    )


def _neutral_with_fallback(
    *,
    host_sentence_text: str,
    destination_title: str,
    phrase_match_state: str,
    destination_phrase_count: int,
    context_window_tokens: int,
) -> PhraseMatchResult:
    fallback = _run_current_fallback(host_sentence_text, destination_title)
    if fallback.anchor_phrase:
        candidate = _build_fallback_candidate(fallback)
        return PhraseMatchResult(
            score_phrase_relevance=candidate.score_phrase_relevance,
            score_phrase_component=candidate.score_phrase_component,
            anchor_phrase=candidate.anchor_phrase,
            anchor_start=candidate.anchor_start,
            anchor_end=candidate.anchor_end,
            anchor_confidence=candidate.anchor_confidence,
            phrase_match_diagnostics=candidate.diagnostics(
                destination_phrase_count=destination_phrase_count,
                context_window_tokens=context_window_tokens,
            ),
        )
    return _neutral_result(
        phrase_match_state=phrase_match_state,
        destination_phrase_count=destination_phrase_count,
        context_window_tokens=context_window_tokens,
    )


def _neutral_result(
    *,
    phrase_match_state: str,
    destination_phrase_count: int,
    context_window_tokens: int,
) -> PhraseMatchResult:
    diagnostics = {
        "score_phrase_relevance": 0.5,
        "phrase_match_state": phrase_match_state,
        "selected_anchor_text": None,
        "selected_anchor_start": None,
        "selected_anchor_end": None,
        "selected_match_type": "none",
        "selected_phrase_source": "none",
        "selected_token_count": 0,
        "context_window_tokens": context_window_tokens,
        "context_corroborating_hits": 0,
        "destination_phrase_count": destination_phrase_count,
    }
    return PhraseMatchResult(
        score_phrase_relevance=0.5,
        score_phrase_component=0.0,
        anchor_phrase=None,
        anchor_start=None,
        anchor_end=None,
        anchor_confidence="none",
        phrase_match_diagnostics=diagnostics,
    )


def _build_destination_phrase_inventory(
    *,
    destination_title: str,
    destination_distilled_text: str,
) -> list[_DestinationPhrase]:
    occurrences: list[_PhraseOccurrence] = []
    source_order = 0
    segment_index = 0

    title = (destination_title or "").strip()
    if title:
        source_order = _collect_phrase_occurrences(
            source_field="title",
            source_rank=0,
            segment_text=title,
            segment_index=segment_index,
            source_order_start=source_order,
            out=occurrences,
        )
        segment_index += 1

    distilled = (destination_distilled_text or "").strip()
    if distilled:
        for raw_segment in _segment_distilled_text(distilled):
            if not raw_segment:
                continue
            source_order = _collect_phrase_occurrences(
                source_field="distilled",
                source_rank=1,
                segment_text=raw_segment,
                segment_index=segment_index,
                source_order_start=source_order,
                out=occurrences,
            )
            segment_index += 1

    if not occurrences:
        return []

    location_map: dict[tuple[str, ...], set[tuple[str, int, int]]] = {}
    grouped_by_start: dict[tuple[str, int, int], list[_PhraseOccurrence]] = {}
    for occurrence in occurrences:
        location_map.setdefault(occurrence.tokens, set()).add(
            (occurrence.source_field, occurrence.segment_index, occurrence.start_index)
        )
        grouped_by_start.setdefault(
            (occurrence.source_field, occurrence.segment_index, occurrence.start_index),
            [],
        ).append(occurrence)

    unique: dict[tuple[str, ...], _DestinationPhrase] = {}
    for occurrence in occurrences:
        same_start_group = grouped_by_start[
            (occurrence.source_field, occurrence.segment_index, occurrence.start_index)
        ]
        has_longer_same_start = any(
            len(other.tokens) > len(occurrence.tokens)
            and other.tokens[: len(occurrence.tokens)] == occurrence.tokens
            for other in same_start_group
        )
        appears_elsewhere = len(location_map.get(occurrence.tokens, set())) > 1
        should_skip_prefix = occurrence.source_field == "title" or (
            occurrence.source_field == "distilled" and len(occurrence.tokens) < 3
        )
        if should_skip_prefix and has_longer_same_start and not appears_elsewhere:
            continue

        candidate = _DestinationPhrase(
            tokens=occurrence.tokens,
            surface=occurrence.surface,
            source_field=occurrence.source_field,
            source_rank=occurrence.source_rank,
            source_order=occurrence.source_order,
        )
        existing = unique.get(candidate.tokens)
        if existing is None or _phrase_sort_key(candidate) < _phrase_sort_key(existing):
            unique[candidate.tokens] = candidate

    phrases = sorted(unique.values(), key=_phrase_sort_key)
    return phrases[:MAX_DESTINATION_PHRASES]


def _collect_phrase_occurrences(
    *,
    source_field: str,
    source_rank: int,
    segment_text: str,
    segment_index: int,
    source_order_start: int,
    out: list[_PhraseOccurrence],
) -> int:
    tokens = _tokenize_with_offsets(segment_text)
    if not tokens:
        return source_order_start

    source_order = source_order_start
    for start_idx in range(len(tokens)):
        max_window = min(MAX_PHRASE_TOKENS, len(tokens) - start_idx)
        for window_size in range(1, max_window + 1):
            phrase_tokens = tuple(
                tokens[token_idx].normalized
                for token_idx in range(start_idx, start_idx + window_size)
            )
            if not _is_allowed_phrase(phrase_tokens, source_field=source_field):
                continue
            first_token = tokens[start_idx]
            last_token = tokens[start_idx + window_size - 1]
            out.append(
                _PhraseOccurrence(
                    tokens=phrase_tokens,
                    surface=segment_text[first_token.start : last_token.end],
                    source_field=source_field,
                    source_rank=source_rank,
                    segment_index=segment_index,
                    start_index=start_idx,
                    source_order=source_order,
                )
            )
            source_order += 1
    return source_order


def _segment_distilled_text(text: str) -> list[str]:
    return [
        segment.strip()
        for segment in _SEGMENT_SPLIT_RE.split(text or "")
        if segment and segment.strip()
    ]


def _tokenize_with_offsets(text: str) -> list[_TokenSpan]:
    spans: list[_TokenSpan] = []
    for match in TOKEN_RE.finditer(text or ""):
        normalized = match.group(0).lower()
        if normalized in STANDARD_ENGLISH_STOPWORDS:
            continue
        spans.append(
            _TokenSpan(normalized=normalized, start=match.start(), end=match.end())
        )
    return spans


def _is_allowed_phrase(tokens: tuple[str, ...], *, source_field: str) -> bool:
    if len(tokens) == 1:
        return source_field == "title" and len(tokens[0]) >= MIN_SINGLE_TOKEN_CHARS
    return 2 <= len(tokens) <= MAX_PHRASE_TOKENS


def _build_host_spans(
    host_sentence_text: str, host_tokens: list[_TokenSpan]
) -> list[_HostSpan]:
    spans: list[_HostSpan] = []
    for start_idx in range(len(host_tokens)):
        max_window = min(MAX_PHRASE_TOKENS, len(host_tokens) - start_idx)
        for window_size in range(1, max_window + 1):
            first_token = host_tokens[start_idx]
            last_token = host_tokens[start_idx + window_size - 1]
            spans.append(
                _HostSpan(
                    start_index=start_idx,
                    end_index=start_idx + window_size - 1,
                    tokens=tuple(
                        host_tokens[token_idx].normalized
                        for token_idx in range(start_idx, start_idx + window_size)
                    ),
                    anchor_start=first_token.start,
                    anchor_end=last_token.end,
                    anchor_phrase=host_sentence_text[
                        first_token.start : last_token.end
                    ],
                )
            )
    return spans


def _count_context_hits(
    *,
    span: _HostSpan,
    host_tokens: list[_TokenSpan],
    host_spans: list[_HostSpan],
    destination_phrases: list[_DestinationPhrase],
    destination_token_set: set[str],
    context_window_tokens: int,
) -> int:
    context_hits = 0
    span_token_set = set(span.tokens)
    window_start = max(0, span.start_index - context_window_tokens)
    window_end = min(len(host_tokens), span.end_index + context_window_tokens + 1)

    context_tokens = [
        host_tokens[token_idx].normalized
        for token_idx in range(window_start, window_end)
        if token_idx < span.start_index or token_idx > span.end_index
    ]
    extra_destination_tokens = {
        token
        for token in context_tokens
        if token in destination_token_set and token not in span_token_set
    }
    if len(extra_destination_tokens) >= 2:
        context_hits += 1

    destination_phrase_map = {phrase.tokens for phrase in destination_phrases}
    if any(
        host_span.tokens in destination_phrase_map
        and (
            host_span.end_index < span.start_index
            or host_span.start_index > span.end_index
        )
        and host_span.start_index >= window_start
        and host_span.end_index < window_end
        for host_span in host_spans
    ):
        context_hits += 1

    return min(context_hits, 2)


def _longest_contiguous_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if HAS_CPP_EXT:
        return int(phrasematch.longest_contiguous_overlap(list(left), list(right)))

    best = 0
    for left_start in range(len(left)):
        for right_start in range(len(right)):
            match_len = 0
            while (
                left_start + match_len < len(left)
                and right_start + match_len < len(right)
                and left[left_start + match_len] == right[right_start + match_len]
            ):
                match_len += 1
            if match_len > best:
                best = match_len
    return best


def _build_match_candidate(
    *,
    span: _HostSpan,
    phrase: _DestinationPhrase,
    match_type: str,
    context_hits: int,
) -> _MatchCandidate:
    is_exact = match_type == "exact"
    selected_phrase_source = phrase.source_field
    phrase_match_state = (
        "computed_exact_title"
        if is_exact and phrase.source_field == "title"
        else "computed_exact_distilled"
        if is_exact
        else "computed_partial_title"
        if phrase.source_field == "title"
        else "computed_partial_distilled"
    )
    score_phrase_relevance = _score_phrase_relevance(
        match_type=match_type,
        source_field=phrase.source_field,
        context_hits=context_hits,
        token_count=span.token_count,
    )
    return _MatchCandidate(
        score_phrase_relevance=score_phrase_relevance,
        anchor_phrase=span.anchor_phrase,
        anchor_start=span.anchor_start,
        anchor_end=span.anchor_end,
        anchor_confidence="strong" if is_exact else "weak",
        phrase_match_state=phrase_match_state,
        selected_match_type=match_type,
        selected_phrase_source=selected_phrase_source,
        selected_token_count=span.token_count,
        context_corroborating_hits=context_hits,
        is_exact=is_exact,
        source_rank=phrase.source_rank,
        sentence_position=span.start_index,
    )


def _build_fallback_candidate(
    fallback,
) -> _MatchCandidate:
    token_count = len(_tokenize_with_offsets(fallback.anchor_phrase or ""))
    score_phrase_relevance = _score_phrase_relevance(
        match_type="exact",
        source_field="title",
        context_hits=0,
        token_count=token_count,
    )
    return _MatchCandidate(
        score_phrase_relevance=score_phrase_relevance,
        anchor_phrase=fallback.anchor_phrase or "",
        anchor_start=fallback.anchor_start or 0,
        anchor_end=fallback.anchor_end or 0,
        anchor_confidence=fallback.anchor_confidence,
        phrase_match_state="fallback_current_extractor",
        selected_match_type="exact",
        selected_phrase_source="fallback",
        selected_token_count=token_count,
        context_corroborating_hits=0,
        is_exact=True,
        source_rank=2,
        sentence_position=fallback.anchor_start or 0,
    )


def _score_phrase_relevance(
    *,
    match_type: str,
    source_field: str,
    context_hits: int,
    token_count: int,
) -> float:
    match_strength = 1.0 if match_type == "exact" else 0.4
    source_strength = 1.0 if source_field == "title" else 0.7
    if match_type == "exact":
        context_strength = 0.0
    elif context_hits <= 0:
        context_strength = 0.0
    elif context_hits == 1:
        context_strength = 0.6
    else:
        context_strength = 1.0

    if token_count <= 1:
        length_strength = 0.2
    elif token_count == 2:
        length_strength = 0.6
    else:
        length_strength = 1.0

    phrase_lift = max(
        0.0,
        min(
            1.0,
            0.55 * match_strength
            + 0.20 * source_strength
            + 0.15 * context_strength
            + 0.10 * length_strength,
        ),
    )
    return max(0.5, min(1.0, 0.5 + 0.5 * phrase_lift))


def _phrase_sort_key(phrase: _DestinationPhrase) -> tuple[int, int, int]:
    return (phrase.source_rank, -phrase.token_count, phrase.source_order)


def _match_sort_key(candidate: _MatchCandidate) -> tuple[float, int, int, int, int]:
    return (
        -candidate.score_phrase_relevance,
        0 if candidate.is_exact else 1,
        candidate.source_rank,
        -candidate.selected_token_count,
        candidate.sentence_position,
    )


def _run_current_fallback(host_sentence_text: str, destination_title: str):
    from .anchor_extractor import extract_anchor

    return extract_anchor(host_sentence_text, destination_title)
