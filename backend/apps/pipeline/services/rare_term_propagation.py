"""FR-010 rare-term propagation across related pages."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, TypeAlias

try:
    from extensions import rareterm
    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

if TYPE_CHECKING:
    from .ranker import ContentRecord


ContentKey: TypeAlias = tuple[int, str]


MINIMUM_TERM_CHARS = 5
MAX_DONOR_PAGES = 5
MAX_TERMS_PER_DONOR = 3
MAX_TERMS_PER_DESTINATION = 8
MAX_TERMS_PER_SUGGESTION = 2
ORIGINAL_DESTINATION_TERMS_PREVIEW = 8

RELATIONSHIP_WEIGHTS = {
    "same_scope": 1.0,
    "same_parent": 0.75,
    "same_grandparent": 0.5,
}


@dataclass(frozen=True, slots=True)
class RareTermPropagationSettings:
    """Operator-facing FR-010 settings."""

    enabled: bool = True
    ranking_weight: float = 0.0
    max_document_frequency: int = 3
    minimum_supporting_related_pages: int = 2


@dataclass(frozen=True, slots=True)
class RelatedPageSummary:
    content_id: int
    relationship_tier: str
    shared_original_token_count: int


@dataclass(frozen=True, slots=True)
class PropagatedRareTerm:
    term: str
    document_frequency: int
    supporting_related_pages: int
    supporting_relationship_weights: tuple[float, ...]
    average_relationship_weight: float
    term_evidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "term": self.term,
            "document_frequency": self.document_frequency,
            "supporting_related_pages": self.supporting_related_pages,
            "supporting_relationship_weights": [
                round(weight, 6)
                for weight in self.supporting_relationship_weights
            ],
            "average_relationship_weight": round(self.average_relationship_weight, 6),
            "term_evidence": round(self.term_evidence, 6),
        }


@dataclass(frozen=True, slots=True)
class RareTermProfile:
    destination_key: ContentKey
    profile_state: str
    original_destination_terms: tuple[str, ...]
    eligible_related_page_count: int
    related_page_summary: tuple[RelatedPageSummary, ...]
    propagated_terms: tuple[PropagatedRareTerm, ...]


@dataclass(frozen=True, slots=True)
class RareTermPropagationResult:
    score_rare_term_propagation: float
    rare_term_component: float
    rare_term_state: str
    rare_term_diagnostics: dict[str, object]


def score_rare_term_component(score_rare_term_propagation: float) -> float:
    """Center the stored FR-010 score for additive ranking."""
    return max(0.0, min(1.0, 2.0 * (float(score_rare_term_propagation) - 0.5)))


def build_rare_term_profiles(
    content_records: Mapping[ContentKey, ContentRecord],
    *,
    settings: RareTermPropagationSettings = RareTermPropagationSettings(),
) -> dict[ContentKey, RareTermProfile]:
    """Build one FR-010 rare-term profile per destination."""
    if not settings.enabled:
        return {}

    document_frequency = _build_document_frequency(content_records)
    profiles: dict[ContentKey, RareTermProfile] = {}
    all_records = list(content_records.values())

    for destination in all_records:
        donors = _select_eligible_donors(destination, all_records)
        related_page_summary = tuple(
            RelatedPageSummary(
                content_id=donor.content_id,
                relationship_tier=relationship_tier,
                shared_original_token_count=shared_token_count,
            )
            for donor, relationship_tier, _relationship_weight, shared_token_count in donors
        )
        original_destination_terms = tuple(sorted(destination.tokens)[:ORIGINAL_DESTINATION_TERMS_PREVIEW])

        if not donors:
            profiles[destination.key] = RareTermProfile(
                destination_key=destination.key,
                profile_state="neutral_no_eligible_related_pages",
                original_destination_terms=original_destination_terms,
                eligible_related_page_count=0,
                related_page_summary=related_page_summary,
                propagated_terms=(),
            )
            continue

        merged_term_support: dict[str, dict[str, object]] = defaultdict(
            lambda: {
                "document_frequency": 0,
                "supporting_page_keys": set(),
                "supporting_relationship_weights": [],
            }
        )
        saw_candidate_term = False

        for donor, _relationship_tier, relationship_weight, _shared_token_count in donors:
            donor_terms = _select_donor_terms(
                donor=donor,
                destination=destination,
                document_frequency=document_frequency,
                settings=settings,
            )
            if donor_terms:
                saw_candidate_term = True
            for term in donor_terms:
                support = merged_term_support[term]
                support["document_frequency"] = document_frequency.get(term, 0)
                support["supporting_page_keys"].add(donor.key)
                support["supporting_relationship_weights"].append(relationship_weight)

        if not saw_candidate_term:
            profiles[destination.key] = RareTermProfile(
                destination_key=destination.key,
                profile_state="neutral_no_rare_terms",
                original_destination_terms=original_destination_terms,
                eligible_related_page_count=len(donors),
                related_page_summary=related_page_summary,
                propagated_terms=(),
            )
            continue

        propagated_terms = _build_propagated_terms(
            merged_term_support=merged_term_support,
            settings=settings,
        )
        if not propagated_terms:
            profiles[destination.key] = RareTermProfile(
                destination_key=destination.key,
                profile_state="neutral_below_min_support",
                original_destination_terms=original_destination_terms,
                eligible_related_page_count=len(donors),
                related_page_summary=related_page_summary,
                propagated_terms=(),
            )
            continue

        profiles[destination.key] = RareTermProfile(
            destination_key=destination.key,
            profile_state="profile_ready",
            original_destination_terms=original_destination_terms,
            eligible_related_page_count=len(donors),
            related_page_summary=related_page_summary,
            propagated_terms=propagated_terms,
        )

    return profiles


def evaluate_rare_term_propagation(
    *,
    destination: ContentRecord,
    host_sentence_tokens: frozenset[str],
    profiles: Mapping[ContentKey, RareTermProfile] | None,
    settings: RareTermPropagationSettings = RareTermPropagationSettings(),
) -> RareTermPropagationResult:
    """Return the FR-010 score plus explainable rare-term diagnostics."""
    try:
        return _evaluate_rare_term_propagation(
            destination=destination,
            host_sentence_tokens=host_sentence_tokens,
            profiles=profiles or {},
            settings=settings,
        )
    except Exception:
        return _neutral_result(
            rare_term_state="neutral_processing_error",
            profile=None,
            settings=settings,
        )


def _evaluate_rare_term_propagation(
    *,
    destination: ContentRecord,
    host_sentence_tokens: frozenset[str],
    profiles: Mapping[ContentKey, RareTermProfile],
    settings: RareTermPropagationSettings,
) -> RareTermPropagationResult:
    if not settings.enabled:
        return _neutral_result(
            rare_term_state="neutral_feature_disabled",
            profile=None,
            settings=settings,
            include_diagnostics=False,
        )

    profile = profiles.get(destination.key)
    if profile is None:
        return _neutral_result(
            rare_term_state="neutral_processing_error",
            profile=None,
            settings=settings,
        )

    if profile.profile_state != "profile_ready":
        return _neutral_result(
            rare_term_state=profile.profile_state,
            profile=profile,
            settings=settings,
        )

    if HAS_CPP_EXT:
        matched, score = rareterm.evaluate_rare_terms(
            [term.term for term in profile.propagated_terms],
            [float(term.term_evidence) for term in profile.propagated_terms],
            [int(term.supporting_related_pages) for term in profile.propagated_terms],
            host_sentence_tokens,
            MAX_TERMS_PER_SUGGESTION,
        )
        if not matched:
            return _neutral_result(
                rare_term_state="neutral_no_host_match",
                profile=profile,
                settings=settings,
            )

        matched_terms = [
            term
            for term in profile.propagated_terms
            if term.term in host_sentence_tokens
        ]
        matched_terms.sort(
            key=lambda term: (
                -term.term_evidence,
                -term.supporting_related_pages,
                term.term,
            )
        )
        top_matches = tuple(matched_terms[:MAX_TERMS_PER_SUGGESTION])
        diagnostics = _build_diagnostics(
            rare_term_state="computed_match",
            profile=profile,
            matched_terms=top_matches,
            settings=settings,
            score=score,
        )
        return RareTermPropagationResult(
            score_rare_term_propagation=score,
            rare_term_component=score_rare_term_component(score),
            rare_term_state="computed_match",
            rare_term_diagnostics=diagnostics,
        )

    matched_terms = [
        term
        for term in profile.propagated_terms
        if term.term in host_sentence_tokens
    ]
    if not matched_terms:
        return _neutral_result(
            rare_term_state="neutral_no_host_match",
            profile=profile,
            settings=settings,
        )

    matched_terms.sort(
        key=lambda term: (
            -term.term_evidence,
            -term.supporting_related_pages,
            term.term,
        )
    )
    top_matches = tuple(matched_terms[:MAX_TERMS_PER_SUGGESTION])
    rare_term_lift = sum(term.term_evidence for term in top_matches) / len(top_matches)
    score = 0.5 + (0.5 * rare_term_lift)
    diagnostics = _build_diagnostics(
        rare_term_state="computed_match",
        profile=profile,
        matched_terms=top_matches,
        settings=settings,
        score=score,
    )
    return RareTermPropagationResult(
        score_rare_term_propagation=score,
        rare_term_component=score_rare_term_component(score),
        rare_term_state="computed_match",
        rare_term_diagnostics=diagnostics,
    )


def _neutral_result(
    *,
    rare_term_state: str,
    profile: RareTermProfile | None,
    settings: RareTermPropagationSettings,
    include_diagnostics: bool = True,
) -> RareTermPropagationResult:
    diagnostics: dict[str, object] = {}
    if include_diagnostics:
        diagnostics = _build_diagnostics(
            rare_term_state=rare_term_state,
            profile=profile,
            matched_terms=(),
            settings=settings,
            score=0.5,
        )
    return RareTermPropagationResult(
        score_rare_term_propagation=0.5,
        rare_term_component=0.0,
        rare_term_state=rare_term_state,
        rare_term_diagnostics=diagnostics,
    )


def _build_diagnostics(
    *,
    rare_term_state: str,
    profile: RareTermProfile | None,
    matched_terms: tuple[PropagatedRareTerm, ...],
    settings: RareTermPropagationSettings,
    score: float,
) -> dict[str, object]:
    propagated_candidates = [
        term.as_dict()
        for term in (profile.propagated_terms if profile else ())
    ]
    return {
        "score_rare_term_propagation": round(score, 6),
        "rare_term_state": rare_term_state,
        "original_destination_terms": list(profile.original_destination_terms if profile else ()),
        "propagated_term_candidates": propagated_candidates,
        "matched_propagated_terms": [term.as_dict() for term in matched_terms],
        "top_propagated_terms": propagated_candidates,
        "eligible_related_page_count": profile.eligible_related_page_count if profile else 0,
        "related_page_summary": [
            {
                "content_id": row.content_id,
                "relationship_tier": row.relationship_tier,
                "shared_original_token_count": row.shared_original_token_count,
            }
            for row in (profile.related_page_summary if profile else ())
        ],
        "max_document_frequency": settings.max_document_frequency,
        "minimum_supporting_related_pages": settings.minimum_supporting_related_pages,
    }


def _build_document_frequency(
    content_records: Mapping[ContentKey, ContentRecord],
) -> Counter[str]:
    document_frequency: Counter[str] = Counter()
    for record in content_records.values():
        document_frequency.update(record.tokens)
    return document_frequency


def _select_eligible_donors(
    destination: ContentRecord,
    all_records: list[ContentRecord],
) -> list[tuple[ContentRecord, str, float, int]]:
    donors: list[tuple[ContentRecord, str, float, int]] = []
    for donor in all_records:
        if donor.key == destination.key:
            continue
        if _is_cross_silo(destination, donor):
            continue
        relationship_tier = _relationship_tier(destination, donor)
        if relationship_tier is None:
            continue
        shared_token_count = len(destination.tokens & donor.tokens)
        minimum_shared_tokens = 1 if relationship_tier == "same_scope" else 2
        if shared_token_count < minimum_shared_tokens:
            continue
        donors.append(
            (
                donor,
                relationship_tier,
                RELATIONSHIP_WEIGHTS[relationship_tier],
                shared_token_count,
            )
        )

    donors.sort(
        key=lambda item: (
            -item[2],
            -item[3],
            item[0].content_id,
            item[0].content_type,
        )
    )
    return donors[:MAX_DONOR_PAGES]


def _is_cross_silo(destination: ContentRecord, donor: ContentRecord) -> bool:
    if destination.silo_group_id is None or donor.silo_group_id is None:
        return False
    return destination.silo_group_id != donor.silo_group_id


def _relationship_tier(
    destination: ContentRecord,
    donor: ContentRecord,
) -> str | None:
    if (
        destination.scope_id > 0
        and donor.scope_id > 0
        and destination.scope_id == donor.scope_id
        and destination.scope_type == donor.scope_type
    ):
        return "same_scope"
    if (
        destination.parent_id is not None
        and donor.parent_id is not None
        and destination.parent_id == donor.parent_id
        and destination.parent_type == donor.parent_type
    ):
        return "same_parent"
    if (
        destination.grandparent_id is not None
        and donor.grandparent_id is not None
        and destination.grandparent_id == donor.grandparent_id
        and destination.grandparent_type == donor.grandparent_type
    ):
        return "same_grandparent"
    return None


def _select_donor_terms(
    *,
    donor: ContentRecord,
    destination: ContentRecord,
    document_frequency: Mapping[str, int],
    settings: RareTermPropagationSettings,
) -> tuple[str, ...]:
    candidate_terms = [
        term
        for term in donor.tokens
        if _is_candidate_rare_term(
            term=term,
            destination=destination,
            document_frequency=document_frequency,
            settings=settings,
        )
    ]
    candidate_terms.sort(
        key=lambda term: (
            document_frequency.get(term, 0),
            term,
        )
    )
    return tuple(candidate_terms[:MAX_TERMS_PER_DONOR])


def _is_candidate_rare_term(
    *,
    term: str,
    destination: ContentRecord,
    document_frequency: Mapping[str, int],
    settings: RareTermPropagationSettings,
) -> bool:
    if term in destination.tokens:
        return False
    if len(term) < MINIMUM_TERM_CHARS:
        return False
    if term.isnumeric():
        return False
    if not any(character.isalpha() for character in term):
        return False
    frequency = int(document_frequency.get(term, 0))
    if frequency <= 0:
        return False
    return frequency <= settings.max_document_frequency


def _build_propagated_terms(
    *,
    merged_term_support: Mapping[str, dict[str, object]],
    settings: RareTermPropagationSettings,
) -> tuple[PropagatedRareTerm, ...]:
    propagated_terms: list[PropagatedRareTerm] = []
    for term, support in merged_term_support.items():
        supporting_page_keys = support["supporting_page_keys"]
        supporting_page_count = len(supporting_page_keys)
        if supporting_page_count < settings.minimum_supporting_related_pages:
            continue
        relationship_weights = tuple(
            float(weight)
            for weight in support["supporting_relationship_weights"]
        )
        average_relationship_weight = sum(relationship_weights) / len(relationship_weights)
        rarity_strength = 1.0 - (
            (int(support["document_frequency"]) - 1)
            / max(settings.max_document_frequency, 1)
        )
        rarity_strength = max(0.0, min(1.0, rarity_strength))
        support_strength = min(1.0, supporting_page_count / 3.0)
        term_evidence = max(
            0.0,
            min(
                1.0,
                0.45 * average_relationship_weight
                + 0.35 * support_strength
                + 0.20 * rarity_strength,
            ),
        )
        propagated_terms.append(
            PropagatedRareTerm(
                term=term,
                document_frequency=int(support["document_frequency"]),
                supporting_related_pages=supporting_page_count,
                supporting_relationship_weights=relationship_weights,
                average_relationship_weight=average_relationship_weight,
                term_evidence=term_evidence,
            )
        )

    propagated_terms.sort(
        key=lambda term: (
            -term.term_evidence,
            -term.supporting_related_pages,
            term.term,
        )
    )
    return tuple(propagated_terms[:MAX_TERMS_PER_DESTINATION])
