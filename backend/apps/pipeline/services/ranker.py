"""Composite scoring and anti-junk selection for link suggestions.

This module is pure Python — no database access. All DB loading is done
by the pipeline service which passes pre-built records into these functions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import heapq
import math
import re
from typing import Mapping, TypeAlias


ContentKey: TypeAlias = tuple[int, str]
ExistingLinkKey: TypeAlias = tuple[ContentKey, ContentKey]

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
STANDARD_ENGLISH_STOPWORDS = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an",
        "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
        "before", "being", "below", "between", "both", "but", "by", "can't",
        "cannot", "could", "couldn't", "did", "didn't", "do", "does",
        "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
        "from", "further", "had", "hadn't", "has", "hasn't", "have",
        "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
        "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
        "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't",
        "it", "it's", "its", "itself", "let's", "me", "more", "most",
        "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on",
        "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
        "out", "over", "own", "same", "shan't", "she", "she'd", "she'll",
        "she's", "should", "shouldn't", "so", "some", "such", "than", "that",
        "that's", "the", "their", "theirs", "them", "themselves", "then",
        "there", "there's", "these", "they", "they'd", "they'll", "they're",
        "they've", "this", "those", "through", "to", "too", "under", "until",
        "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
        "we've", "were", "weren't", "what", "what's", "when", "when's",
        "where", "where's", "which", "while", "who", "who's", "whom", "why",
        "why's", "with", "won't", "would", "wouldn't", "you", "you'd",
        "you'll", "you're", "you've", "your", "yours", "yourself",
        "yourselves",
    }
)


@dataclass(frozen=True, slots=True)
class ContentRecord:
    """Pipeline metadata for a content item."""

    content_id: int
    content_type: str
    title: str
    distilled_text: str
    scope_id: int
    scope_type: str
    parent_id: int | None
    parent_type: str
    grandparent_id: int | None
    grandparent_type: str
    silo_group_id: int | None
    silo_group_name: str
    reply_count: int
    pagerank_score: float
    primary_post_char_count: int
    tokens: frozenset[str]

    @property
    def key(self) -> ContentKey:
        return (self.content_id, self.content_type)


@dataclass(frozen=True, slots=True)
class SentenceRecord:
    """Sentence metadata used during ranking."""

    sentence_id: int
    content_id: int
    content_type: str
    text: str
    char_count: int
    tokens: frozenset[str]

    @property
    def content_key(self) -> ContentKey:
        return (self.content_id, self.content_type)


@dataclass(frozen=True, slots=True)
class SentenceSemanticMatch:
    """Sentence-level semantic score produced by Stage 2."""

    host_content_id: int
    host_content_type: str
    sentence_id: int
    score_semantic: float

    @property
    def host_key(self) -> ContentKey:
        return (self.host_content_id, self.host_content_type)


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """Fully scored candidate suggestion."""

    destination_content_id: int
    destination_content_type: str
    host_content_id: int
    host_content_type: str
    host_sentence_id: int
    score_semantic: float
    score_keyword: float
    score_node_affinity: float
    score_quality: float
    score_silo_affinity: float
    score_final: float

    @property
    def destination_key(self) -> ContentKey:
        return (self.destination_content_id, self.destination_content_type)

    @property
    def host_key(self) -> ContentKey:
        return (self.host_content_id, self.host_content_type)


@dataclass(frozen=True, slots=True)
class SiloSettings:
    """Persisted controls for silo-aware ranking."""

    mode: str = "disabled"
    same_silo_boost: float = 0.0
    cross_silo_penalty: float = 0.0


def classify_silo_relationship(destination: ContentRecord, host: ContentRecord) -> str:
    """Return same, cross, or unassigned for host/destination silo relationship."""
    if destination.silo_group_id is None or host.silo_group_id is None:
        return "unassigned"
    if destination.silo_group_id == host.silo_group_id:
        return "same"
    return "cross"


def score_silo_affinity(
    destination: ContentRecord,
    host: ContentRecord,
    settings: SiloSettings,
) -> float:
    """Calculate the additive silo adjustment for a candidate."""
    if settings.mode != "prefer_same_silo":
        return 0.0

    relationship = classify_silo_relationship(destination, host)
    if relationship == "same":
        return settings.same_silo_boost
    if relationship == "cross":
        return -settings.cross_silo_penalty
    return 0.0


def is_strict_same_silo_blocked(
    destination: ContentRecord,
    host: ContentRecord,
    settings: SiloSettings,
) -> bool:
    """Return True when strict mode should reject a cross-silo candidate."""
    return (
        settings.mode == "strict_same_silo"
        and classify_silo_relationship(destination, host) == "cross"
    )


def tokenize_text(text: str) -> frozenset[str]:
    """Tokenize text for Jaccard scoring, excluding standard English stopwords."""
    tokens = {
        token.lower()
        for token in TOKEN_RE.findall(text)
        if token and token.lower() not in STANDARD_ENGLISH_STOPWORDS
    }
    return frozenset(tokens)


def keyword_jaccard_similarity(
    destination_tokens: frozenset[str],
    sentence_tokens: frozenset[str],
) -> float:
    """Calculate Jaccard similarity across pre-tokenized destination/sentence sets."""
    if not destination_tokens or not sentence_tokens:
        return 0.0
    union = destination_tokens | sentence_tokens
    if not union:
        return 0.0
    return len(destination_tokens & sentence_tokens) / len(union)


def score_node_affinity(destination: ContentRecord, host: ContentRecord) -> float:
    """Score host/destination proximity in the scope tree."""
    if (
        destination.scope_id == host.scope_id
        and destination.scope_type == host.scope_type
    ):
        return 1.0

    if (
        destination.parent_id is not None
        and host.parent_id is not None
        and destination.parent_id == host.parent_id
        and destination.parent_type == host.parent_type
    ):
        return 0.6

    if (
        destination.grandparent_id is not None
        and host.grandparent_id is not None
        and destination.grandparent_id == host.grandparent_id
        and destination.grandparent_type == host.grandparent_type
    ):
        return 0.3

    return 0.0


def log_minmax_normalize_pagerank(
    pagerank_score: float,
    pagerank_min: float,
    pagerank_max: float,
) -> float:
    """Logarithmic min-max normalization for PageRank-based quality override."""
    if pagerank_min == pagerank_max:
        return 0.0

    epsilon = 1e-9
    min_log = math.log(pagerank_min + epsilon)
    max_log = math.log(pagerank_max + epsilon)
    if min_log == max_log:
        return 0.0

    score_log = math.log(pagerank_score + epsilon)
    normalized = (score_log - min_log) / (max_log - min_log)
    return max(0.0, min(1.0, normalized))


def derive_pagerank_bounds(
    content_records: Mapping[ContentKey, ContentRecord],
) -> tuple[float, float]:
    """Return the global min/max PageRank used by the quality override."""
    if not content_records:
        return (0.0, 0.0)
    scores = [record.pagerank_score for record in content_records.values()]
    return (min(scores), max(scores))


def score_destination_matches(
    destination: ContentRecord,
    sentence_matches: list[SentenceSemanticMatch],
    *,
    content_records: Mapping[ContentKey, ContentRecord],
    sentence_records: Mapping[int, SentenceRecord],
    existing_links: set[ExistingLinkKey],
    weights: Mapping[str, float],
    pagerank_bounds: tuple[float, float],
    silo_settings: SiloSettings = SiloSettings(),
    blocked_reasons: set[str] | None = None,
    min_semantic_score: float = 0.25,
    min_sentence_chars: int = 30,
    max_sentence_chars: int = 300,
    min_host_chars: int = 300,
) -> list[ScoredCandidate]:
    """Apply composite scoring plus local anti-junk filters for one destination."""
    pagerank_min, pagerank_max = pagerank_bounds
    ranked: list[ScoredCandidate] = []

    for match in sentence_matches:
        if match.score_semantic < min_semantic_score:
            continue

        host_key = match.host_key
        if host_key == destination.key:
            continue

        if (host_key, destination.key) in existing_links:
            continue

        host_record = content_records.get(host_key)
        sentence_record = sentence_records.get(match.sentence_id)
        if host_record is None or sentence_record is None:
            continue

        if is_strict_same_silo_blocked(destination, host_record, silo_settings):
            if blocked_reasons is not None:
                blocked_reasons.add("cross_silo_blocked")
            continue

        if sentence_record.char_count < min_sentence_chars:
            continue
        if sentence_record.char_count > max_sentence_chars:
            continue

        if (
            host_record.reply_count <= 0
            and host_record.primary_post_char_count <= min_host_chars
        ):
            continue

        score_keyword = keyword_jaccard_similarity(
            destination.tokens,
            sentence_record.tokens,
        )
        score_node = score_node_affinity(destination, host_record)
        score_quality = log_minmax_normalize_pagerank(
            host_record.pagerank_score,
            pagerank_min,
            pagerank_max,
        )
        score_silo = score_silo_affinity(destination, host_record, silo_settings)
        score_final = (
            float(weights.get("w_semantic", 0.0)) * match.score_semantic
            + float(weights.get("w_keyword", 0.0)) * score_keyword
            + float(weights.get("w_node", 0.0)) * score_node
            + float(weights.get("w_quality", 0.0)) * score_quality
            + score_silo
        )

        ranked.append(
            ScoredCandidate(
                destination_content_id=destination.content_id,
                destination_content_type=destination.content_type,
                host_content_id=match.host_content_id,
                host_content_type=match.host_content_type,
                host_sentence_id=match.sentence_id,
                score_semantic=float(match.score_semantic),
                score_keyword=float(score_keyword),
                score_node_affinity=float(score_node),
                score_quality=float(score_quality),
                score_silo_affinity=float(score_silo),
                score_final=float(score_final),
            )
        )

    ranked.sort(
        key=lambda candidate: (
            -candidate.score_final,
            -candidate.score_semantic,
            candidate.host_content_id,
            candidate.host_content_type,
            candidate.host_sentence_id,
        )
    )
    return ranked


def select_final_candidates(
    candidates_by_destination: Mapping[ContentKey, list[ScoredCandidate]],
    *,
    max_host_reuse: int = 3,
    blocked_diagnostics: dict[ContentKey, str] | None = None,
) -> list[ScoredCandidate]:
    """Resolve host-reuse and circular-direction conflicts across destinations.

    If *blocked_diagnostics* is provided, destinations whose candidates are
    all blocked will be recorded with their last blocking reason
    (``"host_reuse_cap"`` or ``"circular_suppressed"``).
    """
    heap: list[tuple[float, float, int, str, int]] = []
    destination_cursor: dict[ContentKey, int] = {}

    for destination_key, candidates in candidates_by_destination.items():
        if not candidates:
            continue
        destination_cursor[destination_key] = 0
        heapq.heappush(
            heap,
            (
                -candidates[0].score_final,
                -candidates[0].score_semantic,
                candidates[0].destination_content_id,
                candidates[0].destination_content_type,
                0,
            ),
        )

    selected_by_destination: dict[ContentKey, ScoredCandidate] = {}
    host_reuse_counts: Counter[ContentKey] = Counter()
    selected_directions: set[tuple[ContentKey, ContentKey]] = set()
    last_block_reason: dict[ContentKey, str] = {}

    while heap:
        _neg_final, _neg_semantic, destination_id, destination_type, candidate_idx = heapq.heappop(heap)
        destination_key = (destination_id, destination_type)
        if destination_key in selected_by_destination:
            continue

        candidates = candidates_by_destination.get(destination_key, [])
        if candidate_idx >= len(candidates):
            continue

        candidate = candidates[candidate_idx]
        is_host_reuse = host_reuse_counts[candidate.host_key] >= max_host_reuse
        is_circular = (candidate.host_key, candidate.destination_key) in selected_directions
        blocked = is_host_reuse or is_circular
        if blocked:
            if is_circular:
                last_block_reason[destination_key] = "circular_suppressed"
            else:
                last_block_reason[destination_key] = "host_reuse_cap"
            next_idx = candidate_idx + 1
            if next_idx < len(candidates):
                next_candidate = candidates[next_idx]
                heapq.heappush(
                    heap,
                    (
                        -next_candidate.score_final,
                        -next_candidate.score_semantic,
                        next_candidate.destination_content_id,
                        next_candidate.destination_content_type,
                        next_idx,
                    ),
                )
            continue

        selected_by_destination[destination_key] = candidate
        host_reuse_counts[candidate.host_key] += 1
        selected_directions.add((candidate.destination_key, candidate.host_key))
        last_block_reason.pop(destination_key, None)

    if blocked_diagnostics is not None:
        for dest_key, reason in last_block_reason.items():
            if dest_key not in selected_by_destination:
                blocked_diagnostics[dest_key] = reason

    return sorted(
        selected_by_destination.values(),
        key=lambda c: (-c.score_final, -c.score_semantic),
    )
