"""FR-011 field-aware relevance scoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

try:
    from extensions import fieldrel

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

from .learned_anchor import KNOWN_NOISE_ANCHORS, LearnedAnchorInputRow
from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE

if TYPE_CHECKING:
    from .ranker import ContentRecord


MAX_MATCHED_TOKENS_PER_FIELD = 5
FIELD_COUNT = 4
BM25_K1 = 1.2
TITLE_B = 0.20
BODY_B = 0.75
SCOPE_B = 0.35
LEARNED_ANCHOR_B = 0.40

REFERENCE_FIELD_LENGTHS = {
    "title": 8.0,
    "body": 120.0,
    "scope": 8.0,
    "learned_anchor": 10.0,
}


@dataclass(frozen=True, slots=True)
class FieldAwareRelevanceSettings:
    """Operator-facing FR-011 settings."""

    ranking_weight: float = 0.0
    title_field_weight: float = 0.40
    body_field_weight: float = 0.30
    scope_field_weight: float = 0.15
    learned_anchor_field_weight: float = 0.15


@dataclass(frozen=True, slots=True)
class FieldAwareRelevanceResult:
    """Stored FR-011 score plus the centered additive component."""

    score_field_aware_relevance: float
    field_aware_component: float
    field_aware_state: str
    field_aware_diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class _FieldProfile:
    name: str
    token_counts: Counter[str]
    field_length: int
    field_weight: float
    b_value: float


def score_field_aware_component(score: float) -> float:
    """Center the stored FR-011 score for additive ranking."""
    return max(0.0, min(1.0, 2.0 * (float(score) - 0.5)))


def evaluate_field_aware_relevance(
    *,
    destination: ContentRecord,
    host_sentence_text: str,
    inbound_anchor_rows: list[LearnedAnchorInputRow],
    settings: FieldAwareRelevanceSettings = FieldAwareRelevanceSettings(),
) -> FieldAwareRelevanceResult:
    """Return the FR-011 score plus explainable field diagnostics."""
    try:
        return _evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text=host_sentence_text,
            inbound_anchor_rows=inbound_anchor_rows,
            settings=settings,
        )
    except Exception:
        return _neutral_result(
            field_aware_state="neutral_processing_error",
            settings=settings,
        )


def _evaluate_field_aware_relevance(
    *,
    destination: ContentRecord,
    host_sentence_text: str,
    inbound_anchor_rows: list[LearnedAnchorInputRow],
    settings: FieldAwareRelevanceSettings,
) -> FieldAwareRelevanceResult:
    field_profiles = _build_field_profiles(
        destination=destination,
        inbound_anchor_rows=inbound_anchor_rows,
        settings=settings,
    )
    total_destination_terms = sum(profile.field_length for profile in field_profiles)
    if total_destination_terms <= 0:
        return _neutral_result(
            field_aware_state="neutral_no_destination_terms",
            settings=settings,
            field_profiles=field_profiles,
        )

    host_token_counts = _token_counts(host_sentence_text)
    if not host_token_counts:
        return _neutral_result(
            field_aware_state="neutral_no_host_terms",
            settings=settings,
            field_profiles=field_profiles,
        )

    field_presence_count = _build_field_presence_count(field_profiles)
    matched_fields: list[tuple[_FieldProfile, float, list[dict[str, object]]]] = []

    for profile in field_profiles:
        field_score, matched_terms = _score_field(
            profile=profile,
            host_token_counts=host_token_counts,
            field_presence_count=field_presence_count,
        )
        if field_score > 0.0:
            matched_fields.append((profile, field_score, matched_terms))

    if not matched_fields:
        return _neutral_result(
            field_aware_state="neutral_no_field_matches",
            settings=settings,
            field_profiles=field_profiles,
        )

    active_weight_sum = sum(
        profile.field_weight for profile, _score, _terms in matched_fields
    )
    combined_field_score = 0.0
    if active_weight_sum > 0:
        combined_field_score = sum(
            (profile.field_weight / active_weight_sum) * field_score
            for profile, field_score, _terms in matched_fields
        )
    combined_field_score = max(0.0, min(1.0, combined_field_score))
    score = 0.5 + (0.5 * combined_field_score)
    diagnostics = _build_diagnostics(
        field_aware_state="computed_match",
        settings=settings,
        field_profiles=field_profiles,
        matched_fields=matched_fields,
        score=score,
    )
    return FieldAwareRelevanceResult(
        score_field_aware_relevance=score,
        field_aware_component=score_field_aware_component(score),
        field_aware_state="computed_match",
        field_aware_diagnostics=diagnostics,
    )


def _neutral_result(
    *,
    field_aware_state: str,
    settings: FieldAwareRelevanceSettings,
    field_profiles: tuple[_FieldProfile, ...] = (),
) -> FieldAwareRelevanceResult:
    return FieldAwareRelevanceResult(
        score_field_aware_relevance=0.5,
        field_aware_component=0.0,
        field_aware_state=field_aware_state,
        field_aware_diagnostics=_build_diagnostics(
            field_aware_state=field_aware_state,
            settings=settings,
            field_profiles=field_profiles,
            matched_fields=[],
            score=0.5,
        ),
    )


def _build_field_profiles(
    *,
    destination: ContentRecord,
    inbound_anchor_rows: list[LearnedAnchorInputRow],
    settings: FieldAwareRelevanceSettings,
) -> tuple[_FieldProfile, ...]:
    learned_anchor_text = _learned_anchor_text(inbound_anchor_rows)
    return (
        _field_profile(
            "title",
            destination.title,
            settings.title_field_weight,
            TITLE_B,
        ),
        _field_profile(
            "body",
            destination.distilled_text,
            settings.body_field_weight,
            BODY_B,
        ),
        _field_profile(
            "scope",
            " ".join(
                part
                for part in [
                    destination.scope_title,
                    destination.parent_scope_title,
                    destination.grandparent_scope_title,
                ]
                if part
            ),
            settings.scope_field_weight,
            SCOPE_B,
        ),
        _field_profile(
            "learned_anchor",
            learned_anchor_text,
            settings.learned_anchor_field_weight,
            LEARNED_ANCHOR_B,
        ),
    )


def _field_profile(
    name: str,
    text: str,
    field_weight: float,
    b_value: float,
) -> _FieldProfile:
    token_counts = _token_counts(text)
    return _FieldProfile(
        name=name,
        token_counts=token_counts,
        field_length=sum(token_counts.values()),
        field_weight=float(field_weight),
        b_value=b_value,
    )


def _build_field_presence_count(
    field_profiles: tuple[_FieldProfile, ...],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for profile in field_profiles:
        counts.update(profile.token_counts.keys())
    return counts


def _score_field(
    *,
    profile: _FieldProfile,
    host_token_counts: Counter[str],
    field_presence_count: Counter[str],
) -> tuple[float, list[dict[str, object]]]:
    if profile.field_length <= 0 or not profile.token_counts:
        return 0.0, []

    scored_terms: list[dict[str, object]] = []
    matched_tokens: list[str] = []
    matched_host_tfs: list[int] = []
    matched_field_tfs: list[int] = []
    matched_field_presence_counts: list[int] = []
    for token, host_tf in host_token_counts.items():
        field_tf = profile.token_counts.get(token, 0)
        if field_tf <= 0:
            continue
        idf = math.log1p(
            (1.0 + FIELD_COUNT) / (1.0 + float(field_presence_count.get(token, 0)))
        )
        tf_norm = _bm25_tf_norm(
            term_frequency=field_tf,
            field_length=profile.field_length,
            reference_length=REFERENCE_FIELD_LENGTHS[profile.name],
            b_value=profile.b_value,
        )
        token_score = tf_norm * idf * min(2.0, float(host_tf))
        scored_terms.append(
            {
                "token": token,
                "field_tf": int(field_tf),
                "host_tf": int(host_tf),
                "field_presence_count": int(field_presence_count.get(token, 0)),
                "idf": round(idf, 6),
                "token_score": round(token_score, 6),
            }
        )
        matched_tokens.append(token)
        matched_host_tfs.append(int(host_tf))
        matched_field_tfs.append(int(field_tf))
        matched_field_presence_counts.append(int(field_presence_count.get(token, 0)))

    if not scored_terms:
        return 0.0, []

    scored_terms.sort(
        key=lambda row: (
            -float(row["token_score"]),
            -int(row["field_tf"]),
            row["token"],
        )
    )
    top_terms = scored_terms[:MAX_MATCHED_TOKENS_PER_FIELD]
    if HAS_CPP_EXT:
        field_score = float(
            fieldrel.score_field_tokens(
                matched_tokens,
                matched_host_tfs,
                matched_field_tfs,
                matched_field_presence_counts,
                int(profile.field_length),
                float(REFERENCE_FIELD_LENGTHS[profile.name]),
                float(profile.b_value),
                int(FIELD_COUNT),
                float(BM25_K1),
                int(MAX_MATCHED_TOKENS_PER_FIELD),
            )
        )
    else:
        field_raw = sum(float(row["token_score"]) for row in top_terms) / len(top_terms)
        field_score = field_raw / (1.0 + field_raw)
    return field_score, top_terms


def _bm25_tf_norm(
    *,
    term_frequency: int,
    field_length: int,
    reference_length: float,
    b_value: float,
) -> float:
    denominator = float(term_frequency) + BM25_K1 * (
        1.0 - b_value + b_value * (float(field_length) / max(1.0, reference_length))
    )
    if denominator <= 0:
        return 0.0
    return (float(term_frequency) * (BM25_K1 + 1.0)) / denominator


def _build_diagnostics(
    *,
    field_aware_state: str,
    settings: FieldAwareRelevanceSettings,
    field_profiles: tuple[_FieldProfile, ...],
    matched_fields: list[tuple[_FieldProfile, float, list[dict[str, object]]]],
    score: float,
) -> dict[str, object]:
    matched_by_name = {
        profile.name: (field_score, matched_terms)
        for profile, field_score, matched_terms in matched_fields
    }
    return {
        "score_field_aware_relevance": round(score, 6),
        "field_aware_state": field_aware_state,
        "field_weights": {
            "title": round(float(settings.title_field_weight), 6),
            "body": round(float(settings.body_field_weight), 6),
            "scope": round(float(settings.scope_field_weight), 6),
            "learned_anchor": round(float(settings.learned_anchor_field_weight), 6),
        },
        "field_lengths": {
            profile.name: profile.field_length for profile in field_profiles
        },
        "matched_field_count": len(matched_fields),
        "field_scores": {
            profile.name: {
                "score": round(
                    float(matched_by_name.get(profile.name, (0.0, []))[0]), 6
                ),
                "matched_terms": matched_by_name.get(profile.name, (0.0, []))[1],
            }
            for profile in field_profiles
        },
    }


def _learned_anchor_text(rows: list[LearnedAnchorInputRow]) -> str:
    cleaned: list[str] = []
    for row in rows:
        raw_text = (row.anchor_text or "").strip()
        normalized_raw = _normalize_noise_text(raw_text)
        if not raw_text or normalized_raw in KNOWN_NOISE_ANCHORS:
            continue
        cleaned.append(raw_text)
    return " ".join(cleaned)


def _token_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for match in TOKEN_RE.finditer(text or ""):
        token = match.group(0).lower()
        if token in STANDARD_ENGLISH_STOPWORDS:
            continue
        counts[token] += 1
    return counts


def _normalize_noise_text(text: str) -> str:
    return " ".join(match.group(0).lower() for match in TOKEN_RE.finditer(text or ""))
