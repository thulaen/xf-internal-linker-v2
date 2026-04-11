"""Pipeline persistence functions.

Extracted from pipeline.py to satisfy file-length limits.
Functions that write Suggestion and PipelineDiagnostic records to the
database live here.
"""

from __future__ import annotations

from typing import Any

from .ranker import (
    ContentKey,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
)


# ---------------------------------------------------------------------------
# Persist suggestions
# ---------------------------------------------------------------------------


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
    """
    from apps.content.models import ContentItem, Sentence
    from apps.suggestions.models import PipelineRun, Suggestion

    try:
        run = PipelineRun.objects.get(run_id=run_id)
    except PipelineRun.DoesNotExist:
        run = None

    valid_candidates: list[ScoredCandidate] = []
    content_item_ids: set[int] = set()
    sentence_ids: set[int] = set()
    destination_ids_to_replace: set[int] = set()

    for candidate in selected_candidates:
        dest_key = candidate.destination_key
        dest_record = content_records.get(dest_key)
        sentence_record = sentence_records.get(candidate.host_sentence_id)
        if dest_record is None or sentence_record is None:
            continue
        valid_candidates.append(candidate)
        content_item_ids.add(candidate.destination_content_id)
        content_item_ids.add(candidate.host_content_id)
        sentence_ids.add(candidate.host_sentence_id)
        if rerun_mode == "full_regenerate":
            destination_ids_to_replace.add(candidate.destination_content_id)

    if not valid_candidates:
        return 0

    content_items = ContentItem.objects.in_bulk(content_item_ids)
    sentences = Sentence.objects.in_bulk(sentence_ids)

    if destination_ids_to_replace:
        Suggestion.objects.filter(
            destination_id__in=destination_ids_to_replace,
            status__in=["pending", "superseded"],
        ).delete()

    to_create = _build_suggestion_records(
        run=run,
        valid_candidates=valid_candidates,
        content_items=content_items,
        sentences=sentences,
    )

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
                score_slate_diversity=candidate.score_slate_diversity,
                slate_diversity_diagnostics=candidate.slate_diversity_diagnostics or {},
                phrase_match_diagnostics=candidate.phrase_match_diagnostics,
                learned_anchor_diagnostics=candidate.learned_anchor_diagnostics,
                rare_term_diagnostics=candidate.rare_term_diagnostics,
                field_aware_diagnostics=candidate.field_aware_diagnostics,
                click_distance_diagnostics=candidate.click_distance_diagnostics,
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
