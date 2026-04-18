"""Pipeline persistence functions.

Extracted from pipeline.py to satisfy file-length limits.
Functions that write Suggestion and PipelineDiagnostic records to the
database live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from .ranker import (
    ContentKey,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
)


# ---------------------------------------------------------------------------
# Persist suggestions
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _CandidatePartition:
    """Result of splitting candidates into valid vs suppressed."""

    valid_candidates: list[ScoredCandidate] = field(default_factory=list)
    content_item_ids: set[int] = field(default_factory=set)
    sentence_ids: set[int] = field(default_factory=set)
    destination_ids_to_replace: set[int] = field(default_factory=set)
    suppressed_diagnostics: list[tuple[int, str, str, dict[str, Any] | None]] = field(
        default_factory=list
    )


def _partition_candidates(
    *,
    selected_candidates: list[ScoredCandidate],
    content_records: dict[ContentKey, ContentRecord],
    sentence_records: dict[int, SentenceRecord],
    suppressed_pairs: set[tuple[int, int]],
    rerun_mode: str,
    suppression_days: int,
) -> _CandidatePartition:
    """Split candidates into valid vs negative-memory-suppressed.

    Skips candidates whose destination or sentence record is missing, and
    those whose ``(host_id, destination_id)`` is in ``suppressed_pairs``. For
    suppressed pairs, records a diagnostic tuple so the caller can emit a
    ``PipelineDiagnostic`` row with ``skip_reason="rejected_recently"``.
    """
    out = _CandidatePartition()
    for candidate in selected_candidates:
        dest_record = content_records.get(candidate.destination_key)
        sentence_record = sentence_records.get(candidate.host_sentence_id)
        if dest_record is None or sentence_record is None:
            continue
        pair_id = (candidate.host_content_id, candidate.destination_content_id)
        if pair_id in suppressed_pairs:
            out.suppressed_diagnostics.append(
                (
                    candidate.destination_content_id,
                    candidate.destination_content_type,
                    "rejected_recently",
                    {
                        "host_content_id": candidate.host_content_id,
                        "suppression_days": suppression_days,
                    },
                )
            )
            continue
        out.valid_candidates.append(candidate)
        out.content_item_ids.add(candidate.destination_content_id)
        out.content_item_ids.add(candidate.host_content_id)
        out.sentence_ids.add(candidate.host_sentence_id)
        if rerun_mode == "full_regenerate":
            out.destination_ids_to_replace.add(candidate.destination_content_id)
    return out


def _persist_suggestions(
    *,
    run_id: str,
    selected_candidates: list[ScoredCandidate],
    content_records: dict[ContentKey, ContentRecord],
    sentence_records: dict[int, SentenceRecord],
    rerun_mode: str,
) -> int:
    """Create Suggestion records for the selected candidates.

    For full_regenerate mode, deletes existing pending/superseded suggestions
    for the same destination before inserting new ones.

    Negative-memory suppression: any candidate whose ``(host_id, destination_id)``
    is recorded in ``RejectedPair`` within ``REJECTED_PAIR_SUPPRESSION_DAYS``
    is skipped and a ``PipelineDiagnostic`` row is emitted with
    ``skip_reason="rejected_recently"`` so the operator can see the
    suppression in the "why no suggestion?" explorer (BLC §3).
    """
    from apps.content.models import ContentItem, Sentence
    from apps.suggestions.models import (
        REJECTED_PAIR_SUPPRESSION_DAYS,
        PipelineRun,
        RejectedPair,
        Suggestion,
    )

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        run = None

    # Load the suppression set once per pipeline run. Empty set when the
    # RejectedPair table is empty → behaviour identical to pre-feature.
    parts = _partition_candidates(
        selected_candidates=selected_candidates,
        content_records=content_records,
        sentence_records=sentence_records,
        suppressed_pairs=RejectedPair.get_suppressed_pair_ids(),
        rerun_mode=rerun_mode,
        suppression_days=REJECTED_PAIR_SUPPRESSION_DAYS,
    )

    # Emit negative-memory diagnostics even if no valid candidates remain, so
    # operators can see suppression counts in the explorer.
    if parts.suppressed_diagnostics:
        _persist_diagnostics(run_id=run_id, diagnostics=parts.suppressed_diagnostics)

    if not parts.valid_candidates:
        return 0

    content_items = ContentItem.objects.in_bulk(parts.content_item_ids)
    sentences = Sentence.objects.in_bulk(parts.sentence_ids)

    to_create = _build_suggestion_records(
        run=run,
        valid_candidates=parts.valid_candidates,
        content_items=content_items,
        sentences=sentences,
    )

    # Wrap delete + bulk_create in a transaction so the database is never
    # left in a state where old suggestions are deleted but new ones
    # failed to insert.
    with transaction.atomic():
        if parts.destination_ids_to_replace:
            Suggestion.objects.filter(
                destination_id__in=parts.destination_ids_to_replace,
                status__in=["pending", "superseded"],
            ).delete()

        if to_create:
            Suggestion.objects.bulk_create(to_create)

    return len(to_create)


def _build_suggestion_records(
    *,
    run: Any,
    valid_candidates: list[ScoredCandidate],
    content_items: dict[int, Any],
    sentences: dict[int, Any],
) -> list[Any]:
    """Build Suggestion model instances from scored candidates."""
    from apps.suggestions.models import Suggestion

    records: list[Suggestion] = []
    for candidate in valid_candidates:
        dest_ci = content_items.get(candidate.destination_content_id)
        host_ci = content_items.get(candidate.host_content_id)
        host_sentence = sentences.get(candidate.host_sentence_id)
        if dest_ci is None or host_ci is None or host_sentence is None:
            continue
        records.append(
            Suggestion(
                pipeline_run=run,
                destination=dest_ci,
                host=host_ci,
                host_sentence=host_sentence,
                destination_title=dest_ci.title,
                host_sentence_text=host_sentence.text,
                anchor_phrase=candidate.anchor_phrase,
                anchor_start=candidate.anchor_start,
                anchor_end=candidate.anchor_end,
                anchor_confidence=candidate.anchor_confidence,
                score_semantic=candidate.score_semantic,
                score_keyword=candidate.score_keyword,
                score_node_affinity=candidate.score_node_affinity,
                score_quality=candidate.score_quality,
                score_march_2026_pagerank=dest_ci.march_2026_pagerank_score,
                score_velocity=dest_ci.velocity_score,
                score_link_freshness=dest_ci.link_freshness_score,
                score_phrase_relevance=candidate.score_phrase_relevance,
                score_learned_anchor_corroboration=candidate.score_learned_anchor_corroboration,
                score_rare_term_propagation=candidate.score_rare_term_propagation,
                score_field_aware_relevance=candidate.score_field_aware_relevance,
                score_ga4_gsc=candidate.score_ga4_gsc,
                score_click_distance=candidate.score_click_distance,
                score_explore_exploit=candidate.score_explore_exploit,
                score_cluster_suppression=candidate.score_cluster_suppression,
                score_anchor_diversity=candidate.score_anchor_diversity,
                score_keyword_stuffing=candidate.score_keyword_stuffing,
                score_link_farm=candidate.score_link_farm,
                score_slate_diversity=candidate.score_slate_diversity,
                slate_diversity_diagnostics=candidate.slate_diversity_diagnostics or {},
                repeated_anchor=candidate.repeated_anchor,
                phrase_match_diagnostics=candidate.phrase_match_diagnostics,
                learned_anchor_diagnostics=candidate.learned_anchor_diagnostics,
                rare_term_diagnostics=candidate.rare_term_diagnostics,
                field_aware_diagnostics=candidate.field_aware_diagnostics,
                click_distance_diagnostics=candidate.click_distance_diagnostics,
                anchor_diversity_diagnostics=candidate.anchor_diversity_diagnostics,
                keyword_stuffing_diagnostics=candidate.keyword_stuffing_diagnostics,
                link_farm_diagnostics=candidate.link_farm_diagnostics,
                explore_exploit_diagnostics=candidate.explore_exploit_diagnostics,
                cluster_diagnostics=candidate.cluster_diagnostics,
                score_final=candidate.score_final,
                status="pending",
            )
        )
    return records


def _persist_diagnostics(
    *,
    run_id: str,
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]],
) -> None:
    """Persist pipeline diagnostics (why-no-suggestion records)."""
    from apps.suggestions.models import PipelineDiagnostic, PipelineRun
    from apps.content.models import ContentItem

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        return

    content_qs = ContentItem.objects.filter(
        pk__in={content_id for content_id, _, _, _ in diagnostics}
    )
    content_items = {
        (content_item.pk, content_item.content_type): content_item
        for content_item in content_qs
    }

    to_create = []
    for content_id, content_type, reason, detail in diagnostics:
        ci = content_items.get((content_id, content_type))
        if ci is None:
            continue
        to_create.append(
            PipelineDiagnostic(
                pipeline_run=run,
                destination=ci,
                skip_reason=reason,
                detail=detail or {},
            )
        )

    if to_create:
        PipelineDiagnostic.objects.bulk_create(to_create, ignore_conflicts=True)
