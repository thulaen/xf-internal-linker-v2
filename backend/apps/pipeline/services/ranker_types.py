"""Shared record types used by the link-suggestion ranker."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from apps.suggestions.recommended_weights import recommended_float, recommended_str


ContentKey: TypeAlias = tuple[int, str]
ExistingLinkKey: TypeAlias = tuple[ContentKey, ContentKey]

_NEUTRAL_SCORE: float = 0.5


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
    march_2026_pagerank_score: float
    link_freshness_score: float
    primary_post_char_count: int
    tokens: frozenset[str]
    content_value_score: float = 0.0
    click_distance_score: float = _NEUTRAL_SCORE
    scope_title: str = ""
    parent_scope_title: str = ""
    grandparent_scope_title: str = ""
    cluster_id: int | None = None
    is_canonical: bool = False
    stemmed_tokens: frozenset[str] = frozenset()
    nlp_metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime.datetime | None = None

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
    position: int = 0
    stemmed_tokens: frozenset[str] = frozenset()
    nlp_metadata: dict[str, Any] = field(default_factory=dict)

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
    score_phrase_relevance: float
    score_learned_anchor_corroboration: float
    score_rare_term_propagation: float
    score_field_aware_relevance: float
    score_ga4_gsc: float
    score_click_distance: float
    score_explore_exploit: float
    score_cluster_suppression: float
    score_final: float
    anchor_phrase: str
    anchor_start: int | None
    anchor_end: int | None
    anchor_confidence: str
    phrase_match_diagnostics: dict[str, object]
    learned_anchor_diagnostics: dict[str, object]
    rare_term_diagnostics: dict[str, object]
    field_aware_diagnostics: dict[str, object]
    cluster_diagnostics: dict[str, object]
    explore_exploit_diagnostics: dict[str, object]
    click_distance_diagnostics: dict[str, object]
    score_anchor_diversity: float = _NEUTRAL_SCORE
    score_keyword_stuffing: float = _NEUTRAL_SCORE
    score_link_farm: float = _NEUTRAL_SCORE
    repeated_anchor: bool = False
    anchor_diversity_diagnostics: dict[str, object] = field(default_factory=dict)
    keyword_stuffing_diagnostics: dict[str, object] = field(default_factory=dict)
    link_farm_diagnostics: dict[str, object] = field(default_factory=dict)
    score_slate_diversity: float | None = field(default=None)
    slate_diversity_diagnostics: dict[str, object] = field(default_factory=dict)
    score_darb: float = 0.0
    score_kmig: float = 0.0
    score_tapb: float = 0.0
    score_kcib: float = 0.0
    score_berp: float = 0.0
    score_hgte: float = 0.0
    score_rsqva: float = 0.0
    darb_diagnostics: dict[str, object] = field(default_factory=dict)
    kmig_diagnostics: dict[str, object] = field(default_factory=dict)
    tapb_diagnostics: dict[str, object] = field(default_factory=dict)
    kcib_diagnostics: dict[str, object] = field(default_factory=dict)
    berp_diagnostics: dict[str, object] = field(default_factory=dict)
    hgte_diagnostics: dict[str, object] = field(default_factory=dict)
    rsqva_diagnostics: dict[str, object] = field(default_factory=dict)
    score_passage_relevance: float = _NEUTRAL_SCORE
    passage_relevance_diagnostics: dict[str, object] = field(default_factory=dict)
    score_embedding_age: float = 1.0

    @property
    def destination_key(self) -> ContentKey:
        return (self.destination_content_id, self.destination_content_type)

    @property
    def host_key(self) -> ContentKey:
        return (self.host_content_id, self.host_content_type)


@dataclass(frozen=True, slots=True)
class ClusteringSettings:
    enabled: bool = False
    similarity_threshold: float = 0.04
    suppression_penalty: float = 20.0


@dataclass(frozen=True, slots=True)
class SiloSettings:
    """Persisted controls for silo-aware ranking."""

    mode: str = recommended_str("silo.mode")
    same_silo_boost: float = recommended_float("silo.same_silo_boost")
    cross_silo_penalty: float = recommended_float("silo.cross_silo_penalty")
