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
    approved_pairs: set[tuple[int, int]] | None = None,
    rerun_mode: str,
    suppression_days: int,
) -> _CandidatePartition:
    """Split candidates into valid vs suppressed.

    Skips candidates whose destination or sentence record is missing, whose
    ``(host_id, destination_id)`` is in ``suppressed_pairs`` (negative memory
    of prior rejections), or whose pair already exists as an approved / applied
    / verified Suggestion (``approved_pairs``).

    Emits diagnostic tuples so the caller can write ``PipelineDiagnostic`` rows:
    - ``skip_reason="rejected_recently"`` for negative-memory suppression
    - ``skip_reason="already_approved"`` for pairs already approved by a reviewer

    The approved-pair filter prevents previously-approved link suggestions from
    re-appearing as new pending items on pipeline re-runs — the reviewer already
    said yes to that exact pair (plan Part 7).
    """
    out = _CandidatePartition()
    approved_pairs = approved_pairs or set()
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
        if pair_id in approved_pairs:
            out.suppressed_diagnostics.append(
                (
                    candidate.destination_content_id,
                    candidate.destination_content_type,
                    "already_approved",
                    {
                        "host_content_id": candidate.host_content_id,
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
    keyword_baseline: Any = None,
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
    #
    # Load approved pairs once per run so re-runs do not surface pending copies
    # of already-approved (host, destination) pairs (plan Part 7). Mirrors the
    # RejectedPair suppression pattern; the diagnostic reason is
    # ``already_approved`` so operators can tell the two apart in the explorer.
    approved_pairs = set(
        Suggestion.objects.filter(
            status__in=("approved", "applied", "verified"),
        ).values_list("host_id", "destination_id")
    )
    parts = _partition_candidates(
        selected_candidates=selected_candidates,
        content_records=content_records,
        sentence_records=sentence_records,
        suppressed_pairs=RejectedPair.get_suppressed_pair_ids(),
        approved_pairs=approved_pairs,
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
        keyword_baseline=keyword_baseline,
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


#: Default Elo rating. Source: Elo 1978, *The Rating of Chessplayers, Past
#: and Present*. Mirrors the ``ContentItem.elo_rating`` model default — the
#: ``elo_rating_refresh`` scheduled job updates the column from review-queue
#: history. Pick #35.
_ELO_DEFAULT_RATING: float = 1500.0


@dataclass(slots=True)
class _PersistenceSnapshots:
    """Pre-loaded artefacts the per-row builders need across the candidate loop."""

    calibration: Any | None
    conformal: Any | None
    ql_stats: Any | None


@dataclass(slots=True)
class _CandidateScalars:
    """Per-row scalars derived from the snapshots before model construction."""

    calibrated_probability: float | None
    uncertainty: float | None
    ql_log_score: float
    conformal_band: tuple[float | None, float | None]


def _safe_load_calibration_snapshot() -> Any | None:
    """Best-effort load of the Platt calibration snapshot."""
    from apps.audit.error_ingest import ingest_error
    from apps.pipeline.services.score_calibrator import (
        load_snapshot as load_calibration_snapshot,
    )

    try:
        return load_calibration_snapshot()
    except Exception as exc:  # noqa: BLE001  # surfaced via ingest_error
        ingest_error(
            job_type="pipeline_persist",
            step="load_calibration_snapshot",
            error_message="Platt calibration snapshot load failed",
            raw_exception=str(exc),
            why="Calibration is advisory; suggestion writes proceed without it.",
        )
        return None


def _safe_load_conformal_snapshot() -> Any | None:
    """Best-effort load of the split-conformal predictor snapshot."""
    from apps.audit.error_ingest import ingest_error
    from apps.pipeline.services.conformal_predictor import (
        load_snapshot as load_conformal_snapshot,
    )

    try:
        return load_conformal_snapshot()
    except Exception as exc:  # noqa: BLE001  # surfaced via ingest_error
        ingest_error(
            job_type="pipeline_persist",
            step="load_conformal_snapshot",
            error_message="Conformal predictor snapshot load failed",
            raw_exception=str(exc),
            why="Confidence band falls back to (None, None) on cold start.",
        )
        return None


def _safe_build_ql_stats(keyword_baseline: Any) -> Any | None:
    """Build ``CollectionStatistics`` from a non-empty keyword baseline."""
    if keyword_baseline is None or getattr(keyword_baseline, "total_terms", 0) <= 0:
        return None
    from apps.audit.error_ingest import ingest_error
    from apps.pipeline.services.query_likelihood import CollectionStatistics

    try:
        return CollectionStatistics(
            collection_term_counts=keyword_baseline.term_counts,
            collection_length=int(keyword_baseline.total_terms),
        )
    except Exception as exc:  # noqa: BLE001  # surfaced via ingest_error
        ingest_error(
            job_type="pipeline_persist",
            step="build_collection_statistics",
            error_message="QL CollectionStatistics build failed",
            raw_exception=str(exc),
            why="Per-row QL falls back to 0.0 — never block suggestion writes.",
        )
        return None


def _load_persistence_snapshots(keyword_baseline: Any) -> _PersistenceSnapshots:
    """Pre-load the three per-pipeline artefacts. Each load is best-effort."""
    return _PersistenceSnapshots(
        calibration=_safe_load_calibration_snapshot(),
        conformal=_safe_load_conformal_snapshot(),
        ql_stats=_safe_build_ql_stats(keyword_baseline),
    )


def _compute_ql_log_score(host_sentence, dest_ci, ql_stats) -> float:
    """Pick #28 — QL-Dirichlet log-score for one (sentence, destination) pair."""
    if ql_stats is None:
        return 0.0
    from apps.audit.error_ingest import ingest_error
    from apps.pipeline.services.query_likelihood import (
        score_document as ql_score_document,
        tokenised_to_counter,
    )
    from apps.pipeline.services.text_tokens import tokenize_text

    try:
        query_tokens = tokenize_text(host_sentence.text or "")
        doc_tokens = tokenize_text(dest_ci.distilled_text or "")
        if not query_tokens or not doc_tokens:
            return 0.0
        result = ql_score_document(
            query_term_counts=tokenised_to_counter(query_tokens),
            document_term_counts=tokenised_to_counter(doc_tokens),
            document_length=len(doc_tokens),
            statistics=ql_stats,
        )
        return float(result.log_score)
    except Exception as exc:  # noqa: BLE001  # surfaced via ingest_error
        ingest_error(
            job_type="pipeline_persist",
            step="compute_ql_log_score",
            error_message="QL-Dirichlet score computation failed",
            raw_exception=str(exc),
            why="Per-row QL is advisory; 0.0 fallback keeps the pipeline writing.",
        )
        return 0.0


def _compute_calibrated_probability(score_final: float, snapshot) -> float | None:
    """Pick #32 — Platt-calibrated probability, or None on cold start."""
    if snapshot is None:
        return None
    from apps.pipeline.services.score_calibrator import calibrate_score

    return calibrate_score(float(score_final), snapshot=snapshot)


def _compute_least_confidence_uncertainty(probability: float | None) -> float | None:
    """Pick #49 — Lewis & Gale 1994 binary least-confidence: ``1 - max(p, 1-p)``."""
    if probability is None:
        return None
    p = float(probability)
    return 1.0 - max(p, 1.0 - p)


def _compute_conformal_band(
    score_final: float, snapshot
) -> tuple[float | None, float | None]:
    """Pick #50 — split-conformal (lower, upper). Cold start returns (None, None)."""
    if snapshot is None:
        return None, None
    interval = snapshot.to_calibration().predict_interval(float(score_final))
    return float(interval.lower), float(interval.upper)


def _build_suggestion_model(  # noqa: forbidden-pattern long-function  # justification: single Suggestion(...) constructor call with 60+ required fields; extracting parts would worsen readability and trigger no-pile-up rules elsewhere.
    *,
    run,
    candidate: ScoredCandidate,
    dest_ci,
    host_ci,
    host_sentence,
    scalars: _CandidateScalars,
):
    """Construct one ``Suggestion`` model from a scored candidate plus its scalars.

    Pulled out of ``_build_suggestion_records`` so the per-row constructor (50+
    field assignments) is testable in isolation. ``getattr`` defaults keep
    older ScoredCandidate fixtures (FR-053 / FR-099-105 fields missing) safe.
    """
    from apps.suggestions.models import Suggestion

    confidence_lower, confidence_upper = scalars.conformal_band
    return Suggestion(
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
        score_embedding_age=candidate.score_embedding_age,
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
        score_darb=getattr(candidate, "score_darb", 0.0),
        score_kmig=getattr(candidate, "score_kmig", 0.0),
        score_tapb=getattr(candidate, "score_tapb", 0.0),
        score_kcib=getattr(candidate, "score_kcib", 0.0),
        score_berp=getattr(candidate, "score_berp", 0.0),
        score_hgte=getattr(candidate, "score_hgte", 0.0),
        score_rsqva=getattr(candidate, "score_rsqva", 0.0),
        darb_diagnostics=getattr(candidate, "darb_diagnostics", {}) or {},
        kmig_diagnostics=getattr(candidate, "kmig_diagnostics", {}) or {},
        tapb_diagnostics=getattr(candidate, "tapb_diagnostics", {}) or {},
        kcib_diagnostics=getattr(candidate, "kcib_diagnostics", {}) or {},
        berp_diagnostics=getattr(candidate, "berp_diagnostics", {}) or {},
        hgte_diagnostics=getattr(candidate, "hgte_diagnostics", {}) or {},
        rsqva_diagnostics=getattr(candidate, "rsqva_diagnostics", {}) or {},
        score_passage_relevance=getattr(candidate, "score_passage_relevance", 0.5),
        passage_relevance_diagnostics=getattr(
            candidate, "passage_relevance_diagnostics", {}
        )
        or {},
        score_final=candidate.score_final,
        calibrated_probability=scalars.calibrated_probability,
        uncertainty_score=scalars.uncertainty,
        score_query_likelihood=scalars.ql_log_score,
        score_elo_rating=float(
            getattr(dest_ci, "elo_rating", _ELO_DEFAULT_RATING) or _ELO_DEFAULT_RATING
        ),
        confidence_lower_bound=confidence_lower,
        confidence_upper_bound=confidence_upper,
        status="pending",
    )


def _build_suggestion_records(
    *,
    run: Any,
    valid_candidates: list[ScoredCandidate],
    content_items: dict[int, Any],
    sentences: dict[int, Any],
    keyword_baseline: Any = None,
) -> list[Any]:
    """Build ``Suggestion`` model instances from scored candidates.

    Pick #28 (QL-Dirichlet), Pick #32 (Platt calibration), Pick #49 (least-
    confidence uncertainty), Pick #50 (split-conformal interval). All snapshots
    load once before the loop; per-row helpers compute the scalars and the
    constructor packs them into the model. Cold-start safe at every stage —
    missing snapshots leave the relevant fields NULL so the Explain panel
    renders dashes instead of fake percentages.
    """
    snapshots = _load_persistence_snapshots(keyword_baseline)
    records: list[Any] = []
    for candidate in valid_candidates:
        dest_ci = content_items.get(candidate.destination_content_id)
        host_ci = content_items.get(candidate.host_content_id)
        host_sentence = sentences.get(candidate.host_sentence_id)
        if dest_ci is None or host_ci is None or host_sentence is None:
            continue
        calibrated = _compute_calibrated_probability(
            candidate.score_final, snapshots.calibration
        )
        scalars = _CandidateScalars(
            calibrated_probability=calibrated,
            uncertainty=_compute_least_confidence_uncertainty(calibrated),
            ql_log_score=_compute_ql_log_score(
                host_sentence, dest_ci, snapshots.ql_stats
            ),
            conformal_band=_compute_conformal_band(
                candidate.score_final, snapshots.conformal
            ),
        )
        records.append(
            _build_suggestion_model(
                run=run,
                candidate=candidate,
                dest_ci=dest_ci,
                host_ci=host_ci,
                host_sentence=host_sentence,
                scalars=scalars,
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
