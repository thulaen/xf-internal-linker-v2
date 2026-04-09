"""FR-009 learned anchor vocabulary and corroboration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE


MAX_ANCHOR_FAMILIES = 8
MAX_ALTERNATES_PER_FAMILY = 5
FAMILY_MIN_OVERLAP_TOKENS = 2
FAMILY_MIN_OVERLAP_RATIO = 0.60
MAX_SMALL_VARIANT_EDIT_DISTANCE = 1
NEUTRAL_LEARNED_ANCHOR_SCORE = 0.5
KNOWN_NOISE_ANCHORS = frozenset(
    {
        "click here",
        "here",
        "read more",
        "this link",
        "link",
        "source",
        "website",
        "visit site",
    }
)


@dataclass(frozen=True, slots=True)
class LearnedAnchorSettings:
    ranking_weight: float = 0.0
    minimum_anchor_sources: int = 2
    minimum_family_support_share: float = 0.15
    enable_noise_filter: bool = True


@dataclass(frozen=True, slots=True)
class LearnedAnchorInputRow:
    source_content_id: int
    anchor_text: str


@dataclass(frozen=True, slots=True)
class _AnchorVariant:
    tokens: tuple[str, ...]
    display_text: str
    support_share: float
    supporting_source_count: int
    source_ids: frozenset[int]
    most_common_surface_count: int

    @property
    def normalized_text(self) -> str:
        return " ".join(self.tokens)


@dataclass(frozen=True, slots=True)
class _AnchorFamily:
    canonical_display: str
    canonical_tokens: tuple[str, ...]
    support_share: float
    supporting_source_count: int
    source_ids: frozenset[int]
    variants: tuple[_AnchorVariant, ...]


@dataclass(frozen=True, slots=True)
class LearnedAnchorResult:
    score_learned_anchor_corroboration: float
    learned_anchor_component: float
    learned_anchor_state: str
    learned_anchor_diagnostics: dict[str, object]


def score_learned_anchor_component(score: float) -> float:
    """Convert the stored FR-009 score into a positive-only ranker component."""
    return max(0.0, min(1.0, 2.0 * (float(score) - 0.5)))


def evaluate_learned_anchor_corroboration(
    *,
    candidate_anchor_text: str | None,
    host_sentence_text: str,
    inbound_anchor_rows: list[LearnedAnchorInputRow],
    settings: LearnedAnchorSettings = LearnedAnchorSettings(),
) -> LearnedAnchorResult:
    """Return the FR-009 score plus explainable learned-anchor diagnostics."""
    try:
        return _evaluate_learned_anchor_corroboration(
            candidate_anchor_text=candidate_anchor_text,
            host_sentence_text=host_sentence_text,
            inbound_anchor_rows=inbound_anchor_rows,
            settings=settings,
        )
    except Exception:
        diagnostics = _base_diagnostics(
            candidate_anchor_text=candidate_anchor_text,
            candidate_anchor_tokens=(),
            learned_anchor_state="neutral_processing_error",
            usable_inbound_anchor_sources=0,
            families=(),
        )
        diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
        return LearnedAnchorResult(
            score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
            learned_anchor_component=0.0,
            learned_anchor_state="neutral_processing_error",
            learned_anchor_diagnostics=diagnostics,
        )


def _evaluate_learned_anchor_corroboration(
    *,
    candidate_anchor_text: str | None,
    host_sentence_text: str,
    inbound_anchor_rows: list[LearnedAnchorInputRow],
    settings: LearnedAnchorSettings,
) -> LearnedAnchorResult:
    variants, usable_inbound_anchor_sources = _build_variants(
        inbound_anchor_rows,
        enable_noise_filter=settings.enable_noise_filter,
    )
    families = _build_families(variants, usable_inbound_anchor_sources)
    candidate_anchor_tokens = _normalize_anchor_tokens(candidate_anchor_text or "")

    if usable_inbound_anchor_sources == 0 or not families:
        diagnostics = _base_diagnostics(
            candidate_anchor_text=candidate_anchor_text,
            candidate_anchor_tokens=candidate_anchor_tokens,
            learned_anchor_state="neutral_no_learned_anchor_data",
            usable_inbound_anchor_sources=usable_inbound_anchor_sources,
            families=families,
        )
        diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
        return LearnedAnchorResult(
            score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
            learned_anchor_component=0.0,
            learned_anchor_state="neutral_no_learned_anchor_data",
            learned_anchor_diagnostics=diagnostics,
        )

    if usable_inbound_anchor_sources < settings.minimum_anchor_sources:
        diagnostics = _base_diagnostics(
            candidate_anchor_text=candidate_anchor_text,
            candidate_anchor_tokens=candidate_anchor_tokens,
            learned_anchor_state="neutral_below_min_sources",
            usable_inbound_anchor_sources=usable_inbound_anchor_sources,
            families=families,
        )
        diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
        return LearnedAnchorResult(
            score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
            learned_anchor_component=0.0,
            learned_anchor_state="neutral_below_min_sources",
            learned_anchor_diagnostics=diagnostics,
        )

    if not candidate_anchor_tokens:
        diagnostics = _base_diagnostics(
            candidate_anchor_text=candidate_anchor_text,
            candidate_anchor_tokens=candidate_anchor_tokens,
            learned_anchor_state="neutral_no_anchor_candidate",
            usable_inbound_anchor_sources=usable_inbound_anchor_sources,
            families=families,
        )
        diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
        return LearnedAnchorResult(
            score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
            learned_anchor_component=0.0,
            learned_anchor_state="neutral_no_anchor_candidate",
            learned_anchor_diagnostics=diagnostics,
        )

    exact_match = _find_exact_variant_match(candidate_anchor_tokens, families)
    if exact_match is not None:
        family, variant = exact_match
        if family.support_share >= settings.minimum_family_support_share:
            return _accepted_result(
                learned_anchor_state="exact_variant_match",
                candidate_anchor_text=candidate_anchor_text,
                candidate_anchor_tokens=candidate_anchor_tokens,
                usable_inbound_anchor_sources=usable_inbound_anchor_sources,
                families=families,
                matched_family=family,
                matched_variant=variant,
            )

    family_match = _find_family_match(candidate_anchor_tokens, families)
    if family_match is not None:
        family, variant = family_match
        if family.support_share >= settings.minimum_family_support_share:
            return _accepted_result(
                learned_anchor_state="family_match",
                candidate_anchor_text=candidate_anchor_text,
                candidate_anchor_tokens=candidate_anchor_tokens,
                usable_inbound_anchor_sources=usable_inbound_anchor_sources,
                families=families,
                matched_family=family,
                matched_variant=variant,
            )

    canonical_family = _find_host_canonical_variant(host_sentence_text, families)
    if canonical_family is not None:
        diagnostics = _base_diagnostics(
            candidate_anchor_text=candidate_anchor_text,
            candidate_anchor_tokens=candidate_anchor_tokens,
            learned_anchor_state="host_contains_canonical_variant",
            usable_inbound_anchor_sources=usable_inbound_anchor_sources,
            families=families,
            matched_family=canonical_family,
            host_contains_canonical_variant=True,
            recommended_canonical_anchor=canonical_family.canonical_display,
        )
        diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
        diagnostics["matched_family_canonical"] = canonical_family.canonical_display
        diagnostics["family_support_share"] = round(canonical_family.support_share, 6)
        diagnostics["supporting_source_count"] = (
            canonical_family.supporting_source_count
        )
        return LearnedAnchorResult(
            score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
            learned_anchor_component=0.0,
            learned_anchor_state="host_contains_canonical_variant",
            learned_anchor_diagnostics=diagnostics,
        )

    diagnostics = _base_diagnostics(
        candidate_anchor_text=candidate_anchor_text,
        candidate_anchor_tokens=candidate_anchor_tokens,
        learned_anchor_state="neutral_no_family_match",
        usable_inbound_anchor_sources=usable_inbound_anchor_sources,
        families=families,
    )
    diagnostics["score_learned_anchor_corroboration"] = NEUTRAL_LEARNED_ANCHOR_SCORE
    return LearnedAnchorResult(
        score_learned_anchor_corroboration=NEUTRAL_LEARNED_ANCHOR_SCORE,
        learned_anchor_component=0.0,
        learned_anchor_state="neutral_no_family_match",
        learned_anchor_diagnostics=diagnostics,
    )


def _accepted_result(
    *,
    learned_anchor_state: str,
    candidate_anchor_text: str | None,
    candidate_anchor_tokens: tuple[str, ...],
    usable_inbound_anchor_sources: int,
    families: tuple[_AnchorFamily, ...],
    matched_family: _AnchorFamily,
    matched_variant: _AnchorVariant,
) -> LearnedAnchorResult:
    match_strength = 1.0 if learned_anchor_state == "exact_variant_match" else 0.65
    family_support_strength = _clamp(matched_family.support_share, 0.0, 1.0)
    variant_share_strength = (
        matched_variant.support_share
        if learned_anchor_state == "exact_variant_match"
        else 0.0
    )
    source_count_strength = min(1.0, matched_family.supporting_source_count / 5.0)
    corroboration_lift = _clamp(
        0.45 * match_strength
        + 0.25 * family_support_strength
        + 0.15 * variant_share_strength
        + 0.15 * source_count_strength,
        0.0,
        1.0,
    )
    score = 0.5 + (0.5 * corroboration_lift)
    diagnostics = _base_diagnostics(
        candidate_anchor_text=candidate_anchor_text,
        candidate_anchor_tokens=candidate_anchor_tokens,
        learned_anchor_state=learned_anchor_state,
        usable_inbound_anchor_sources=usable_inbound_anchor_sources,
        families=families,
        matched_family=matched_family,
        matched_variant=matched_variant,
        recommended_canonical_anchor=matched_family.canonical_display,
    )
    diagnostics["score_learned_anchor_corroboration"] = round(score, 6)
    diagnostics["matched_family_canonical"] = matched_family.canonical_display
    diagnostics["matched_variant_display"] = matched_variant.display_text
    diagnostics["family_support_share"] = round(matched_family.support_share, 6)
    diagnostics["variant_support_share"] = round(matched_variant.support_share, 6)
    diagnostics["supporting_source_count"] = matched_family.supporting_source_count
    return LearnedAnchorResult(
        score_learned_anchor_corroboration=score,
        learned_anchor_component=score_learned_anchor_component(score),
        learned_anchor_state=learned_anchor_state,
        learned_anchor_diagnostics=diagnostics,
    )


def _build_variants(
    rows: list[LearnedAnchorInputRow],
    *,
    enable_noise_filter: bool,
) -> tuple[tuple[_AnchorVariant, ...], int]:
    source_ids_by_variant: dict[tuple[str, ...], set[int]] = {}
    surface_counts_by_variant: dict[tuple[str, ...], Counter[str]] = {}
    usable_source_ids: set[int] = set()

    for row in rows:
        display_text = (row.anchor_text or "").strip()
        tokens = _normalize_anchor_tokens(display_text)
        normalized_text = " ".join(tokens)
        raw_normalized_text = _normalize_noise_text(display_text)
        if not tokens:
            continue
        if enable_noise_filter and (
            normalized_text in KNOWN_NOISE_ANCHORS
            or raw_normalized_text in KNOWN_NOISE_ANCHORS
        ):
            continue
        usable_source_ids.add(int(row.source_content_id))
        source_ids_by_variant.setdefault(tokens, set()).add(int(row.source_content_id))
        surface_counts_by_variant.setdefault(tokens, Counter())[display_text] += 1

    usable_inbound_anchor_sources = len(usable_source_ids)
    if usable_inbound_anchor_sources == 0:
        return (), 0

    variants: list[_AnchorVariant] = []
    for tokens, source_ids in source_ids_by_variant.items():
        counter = surface_counts_by_variant.get(tokens, Counter())
        display_text, most_common_surface_count = _choose_display_text(counter, tokens)
        variants.append(
            _AnchorVariant(
                tokens=tokens,
                display_text=display_text,
                support_share=len(source_ids) / usable_inbound_anchor_sources,
                supporting_source_count=len(source_ids),
                source_ids=frozenset(source_ids),
                most_common_surface_count=most_common_surface_count,
            )
        )

    variants.sort(key=_variant_sort_key)
    return tuple(variants), usable_inbound_anchor_sources


def _build_families(
    variants: tuple[_AnchorVariant, ...],
    usable_inbound_anchor_sources: int,
) -> tuple[_AnchorFamily, ...]:
    if not variants or usable_inbound_anchor_sources <= 0:
        return ()

    parent = list(range(len(variants)))

    def _find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def _union(left_index: int, right_index: int) -> None:
        left_root = _find(left_index)
        right_root = _find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left_variant in enumerate(variants):
        for right_index in range(left_index + 1, len(variants)):
            if _variants_belong_together(
                left_variant.tokens, variants[right_index].tokens
            ):
                _union(left_index, right_index)

    grouped: dict[int, list[_AnchorVariant]] = {}
    for index, variant in enumerate(variants):
        grouped.setdefault(_find(index), []).append(variant)

    families: list[_AnchorFamily] = []
    for family_variants in grouped.values():
        ordered_variants = tuple(sorted(family_variants, key=_variant_sort_key))
        canonical_variant = ordered_variants[0]
        family_source_ids = frozenset(
            source_id
            for variant in ordered_variants
            for source_id in variant.source_ids
        )
        support_share = len(family_source_ids) / usable_inbound_anchor_sources
        families.append(
            _AnchorFamily(
                canonical_display=canonical_variant.display_text,
                canonical_tokens=canonical_variant.tokens,
                support_share=support_share,
                supporting_source_count=len(family_source_ids),
                source_ids=family_source_ids,
                variants=ordered_variants,
            )
        )

    families.sort(key=_family_sort_key)
    return tuple(families[:MAX_ANCHOR_FAMILIES])


def _find_exact_variant_match(
    candidate_tokens: tuple[str, ...],
    families: tuple[_AnchorFamily, ...],
) -> tuple[_AnchorFamily, _AnchorVariant] | None:
    best_match: tuple[_AnchorFamily, _AnchorVariant] | None = None
    for family in families:
        for variant in family.variants:
            if candidate_tokens != variant.tokens:
                continue
            if best_match is None or _matched_variant_sort_key(
                family, variant
            ) < _matched_variant_sort_key(*best_match):
                best_match = (family, variant)
    return best_match


def _find_family_match(
    candidate_tokens: tuple[str, ...],
    families: tuple[_AnchorFamily, ...],
) -> tuple[_AnchorFamily, _AnchorVariant] | None:
    best_match: tuple[_AnchorFamily, _AnchorVariant] | None = None
    for family in families:
        for variant in family.variants:
            if candidate_tokens == variant.tokens:
                continue
            if not _variants_belong_together(candidate_tokens, variant.tokens):
                continue
            if best_match is None or _matched_variant_sort_key(
                family, variant
            ) < _matched_variant_sort_key(*best_match):
                best_match = (family, variant)
    return best_match


def _find_host_canonical_variant(
    host_sentence_text: str,
    families: tuple[_AnchorFamily, ...],
) -> _AnchorFamily | None:
    for family in families:
        if _sentence_contains_tokens(host_sentence_text, family.canonical_tokens):
            return family
    return None


def _base_diagnostics(
    *,
    candidate_anchor_text: str | None,
    candidate_anchor_tokens: tuple[str, ...],
    learned_anchor_state: str,
    usable_inbound_anchor_sources: int,
    families: tuple[_AnchorFamily, ...],
    matched_family: _AnchorFamily | None = None,
    matched_variant: _AnchorVariant | None = None,
    host_contains_canonical_variant: bool = False,
    recommended_canonical_anchor: str | None = None,
) -> dict[str, object]:
    top_families = [
        {
            "canonical_anchor": family.canonical_display,
            "support_share": round(family.support_share, 6),
            "supporting_source_count": family.supporting_source_count,
            "alternate_variants": [
                variant.display_text
                for variant in family.variants
                if variant.display_text != family.canonical_display
            ][:MAX_ALTERNATES_PER_FAMILY],
        }
        for family in families
    ]
    return {
        "score_learned_anchor_corroboration": NEUTRAL_LEARNED_ANCHOR_SCORE,
        "learned_anchor_state": learned_anchor_state,
        "candidate_anchor_text": candidate_anchor_text or None,
        "candidate_anchor_normalized": " ".join(candidate_anchor_tokens) or None,
        "matched_family_canonical": matched_family.canonical_display
        if matched_family
        else None,
        "matched_variant_display": matched_variant.display_text
        if matched_variant
        else None,
        "family_support_share": round(matched_family.support_share, 6)
        if matched_family
        else 0.0,
        "variant_support_share": round(matched_variant.support_share, 6)
        if matched_variant
        else 0.0,
        "supporting_source_count": matched_family.supporting_source_count
        if matched_family
        else 0,
        "usable_inbound_anchor_sources": usable_inbound_anchor_sources,
        "learned_family_count": len(families),
        "top_learned_families": top_families,
        "host_contains_canonical_variant": host_contains_canonical_variant,
        "recommended_canonical_anchor": recommended_canonical_anchor,
    }


def _normalize_anchor_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text or ""):
        token = match.group(0).lower()
        if token in STANDARD_ENGLISH_STOPWORDS:
            continue
        tokens.append(token)
    return tuple(tokens)


def _normalize_noise_text(text: str) -> str:
    return " ".join(match.group(0).lower() for match in TOKEN_RE.finditer(text or ""))


def _choose_display_text(
    counter: Counter[str], tokens: tuple[str, ...]
) -> tuple[str, int]:
    if not counter:
        normalized = " ".join(tokens)
        return normalized, 0
    winner = sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))[0]
    return winner[0], winner[1]


def _variant_sort_key(variant: _AnchorVariant) -> tuple[float, float, int, int, str]:
    return (
        -variant.supporting_source_count,
        -variant.support_share,
        -len(variant.tokens),
        -variant.most_common_surface_count,
        variant.display_text.lower(),
    )


def _family_sort_key(family: _AnchorFamily) -> tuple[float, int, int, str]:
    return (
        -family.support_share,
        -family.supporting_source_count,
        -len(family.canonical_tokens),
        family.canonical_display.lower(),
    )


def _matched_variant_sort_key(
    family: _AnchorFamily,
    variant: _AnchorVariant,
) -> tuple[float, int, float, str]:
    return (
        -family.support_share,
        -family.supporting_source_count,
        -variant.support_share,
        family.canonical_display.lower(),
    )


def _variants_belong_together(
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
) -> bool:
    if left_tokens == right_tokens:
        return True
    if not left_tokens or not right_tokens:
        return False
    overlap_len = _longest_contiguous_overlap(left_tokens, right_tokens)
    if overlap_len >= FAMILY_MIN_OVERLAP_TOKENS:
        shorter = min(len(left_tokens), len(right_tokens))
        if overlap_len / shorter >= FAMILY_MIN_OVERLAP_RATIO:
            return True
    if _has_single_prefix_or_suffix_extension(left_tokens, right_tokens):
        return True
    if max(len(left_tokens), len(right_tokens)) <= 2:
        left_text = " ".join(left_tokens)
        right_text = " ".join(right_tokens)
        if _edit_distance(left_text, right_text) <= MAX_SMALL_VARIANT_EDIT_DISTANCE:
            return True
    return False


def _longest_contiguous_overlap(
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
) -> int:
    best = 0
    for left_start in range(len(left_tokens)):
        for right_start in range(len(right_tokens)):
            match_len = 0
            while (
                left_start + match_len < len(left_tokens)
                and right_start + match_len < len(right_tokens)
                and left_tokens[left_start + match_len]
                == right_tokens[right_start + match_len]
            ):
                match_len += 1
            if match_len > best:
                best = match_len
    return best


def _has_single_prefix_or_suffix_extension(
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
) -> bool:
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    if len(longer) != len(shorter) + 1:
        return False
    return shorter == longer[:-1] or shorter == longer[1:]


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (
                0 if left_char == right_char else 1
            )
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


def _sentence_contains_tokens(
    sentence_text: str,
    tokens: tuple[str, ...],
) -> bool:
    if not tokens:
        return False
    sentence_tokens = _normalize_anchor_tokens(sentence_text)
    if len(sentence_tokens) < len(tokens):
        return False
    window_size = len(tokens)
    for start_index in range(0, len(sentence_tokens) - window_size + 1):
        if sentence_tokens[start_index : start_index + window_size] == tokens:
            return True
    return False


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
