"""Main suggestion pipeline service.

3-stage retrieval pipeline:
  Stage 1 — coarse cosine similarity between destination and host-content embeddings
  Stage 2 — fine-grained sentence-level cosine similarity
  Stage 3 — composite scoring (semantic + keyword + node affinity + quality)

V2 changes from V1:
  - Replaces raw SQLite + .npy file artifacts with Django ORM + pgvector VectorField
  - Replaces Flask mark_job_progress with the channel-layer _publish_progress helper
  - All data is loaded from PostgreSQL (ContentItem.embedding, Sentence.embedding)
  - Supports rerun_modes: skip_pending, supersede_pending, full_regenerate
"""

from __future__ import annotations

import gc
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pyarrow as pa
import pyroaring as pr
 
try:
    from extensions import inv_index, strpool
    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

from .click_distance import ClickDistanceSettings, ClickDistanceService
from .feedback_rerank import FeedbackRerankSettings, FeedbackRerankService
from .field_aware_relevance import FieldAwareRelevanceSettings
from .learned_anchor import LearnedAnchorInputRow, LearnedAnchorSettings
from .ranker import (
    ContentKey,
    ContentRecord,
    ExistingLinkKey,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    derive_march_2026_pagerank_bounds,
    score_destination_matches,
    select_final_candidates,
)
from .text_tokens import tokenize_text
from .phrase_matching import PhraseMatchingSettings
from .rare_term_propagation import (
    RareTermPropagationSettings,
    build_rare_term_profiles,
)

logger = logging.getLogger(__name__)

STAGE1_TOP_K = 50
STAGE2_TOP_K = 10
FALLBACK_CANDIDATES_PER_DESTINATION = 5
BLOCK_SIZE = 256

DEFAULT_WEIGHTS = {
    "w_semantic": 0.55,
    "w_keyword": 0.20,
    "w_node": 0.10,
    "w_quality": 0.15,
}


@dataclass
class PipelineResult:
    run_id: str
    items_in_scope: int
    suggestions_created: int
    suggestions_skipped: int


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    run_id: str,
    *,
    rerun_mode: str = "skip_pending",
    destination_scope_ids: set[int] | None = None,
    host_scope_ids: set[int] | None = None,
    progress_fn: Callable[[float, str], None] | None = None,
) -> PipelineResult:
    """Execute the full 3-stage ML suggestion pipeline.

    Args:
        run_id: UUID string of the PipelineRun record.
        rerun_mode: 'skip_pending' | 'supersede_pending' | 'full_regenerate'
        destination_scope_ids: Restrict destinations to these ScopeItem PKs.
        host_scope_ids: Restrict hosts to these ScopeItem PKs.
        progress_fn: Optional callback(progress_0_to_1, message) for live updates.
    """

    def _progress(pct: float, msg: str) -> None:
        logger.info("[run=%s] %.0f%% — %s", run_id, pct * 100, msg)
        if progress_fn:
            progress_fn(pct, msg)

    suggestions_created = 0
    items_in_scope = 0

    _progress(0.02, "Loading settings and weights...")
    weights = _load_weights()
    silo_settings = _load_silo_settings()
    weighted_authority_settings = _load_weighted_authority_settings()
    link_freshness_settings = _load_link_freshness_settings()
    phrase_matching_settings = _load_phrase_matching_settings()
    learned_anchor_settings = _load_learned_anchor_settings()
    rare_term_settings = _load_rare_term_propagation_settings()
    field_aware_settings = _load_field_aware_relevance_settings()
    ga4_gsc_settings = _load_ga4_gsc_settings()
    click_distance_settings = _load_click_distance_settings()
    feedback_rerank_settings = _load_feedback_rerank_settings()

    _progress(0.04, "Initializing feedback reranker...")
    feedback_rerank_service = FeedbackRerankService(feedback_rerank_settings)
    if feedback_rerank_settings.enabled:
        feedback_rerank_service.load_historical_stats()

    _progress(0.05, "Loading content records...")
    content_records = _load_content_records(
        destination_scope_ids=destination_scope_ids,
        host_scope_ids=host_scope_ids,
    )
    if not content_records:
        _progress(1.0, "No content records found — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=0,
            suggestions_created=0,
            suggestions_skipped=0,
        )

    _progress(0.08, "Loading sentence records...")
    sentence_records, content_to_sentence_ids = _load_sentence_records(
        set(content_records.keys())
    )

    _progress(0.12, "Loading existing links...")
    existing_links = _load_existing_links()
    learned_anchor_rows_by_destination = _load_learned_anchor_rows_by_destination()
    rare_term_profiles = {}
    if rare_term_settings.enabled:
        _progress(0.14, "Building rare-term propagation profiles...")
        rare_term_source_records = (
            content_records
            if destination_scope_ids is None and host_scope_ids is None
            else _load_content_records()
        )
        rare_term_profiles = build_rare_term_profiles(
            rare_term_source_records,
            settings=rare_term_settings,
        )

    _progress(0.15, "Applying rerun mode filter...")
    pending_destinations = _get_pending_destinations(rerun_mode)
    if rerun_mode == "supersede_pending":
        _supersede_pending_suggestions(list(content_records.keys()))

    _progress(0.18, "Loading destination embeddings from pgvector...")
    destination_keys, dest_embeddings = _load_destination_embeddings(
        content_records,
        pending_destinations=pending_destinations,
    )
    items_in_scope = len(destination_keys)

    if items_in_scope == 0:
        _progress(1.0, "No destinations to process — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=0,
            suggestions_created=0,
            suggestions_skipped=0,
        )

    _progress(0.22, "Loading sentence embeddings from pgvector...")
    sentence_ids_ordered, sentence_embeddings = _load_sentence_embeddings(
        set(content_records.keys())
    )

    if sentence_embeddings.shape[0] == 0:
        _progress(1.0, "No sentence embeddings available — pipeline complete.")
        return PipelineResult(
            run_id=run_id,
            items_in_scope=items_in_scope,
            suggestions_created=0,
            suggestions_skipped=items_in_scope,
        )

    march_2026_pagerank_bounds = derive_march_2026_pagerank_bounds(content_records)

    _progress(0.25, "Stage 1: coarse content-level candidate retrieval...")
    stage1_candidates: dict[ContentKey, list[int]] = _stage1_candidates(
        destination_keys=destination_keys,
        dest_embeddings=dest_embeddings,
        content_records=content_records,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=STAGE1_TOP_K,
        block_size=BLOCK_SIZE,
    )

    _progress(0.50, "Stage 2+3: sentence scoring and ranking...")
    candidates_by_destination: dict[ContentKey, list[ScoredCandidate]] = {}
    diagnostics: list[tuple[int, str, str, dict[str, Any] | None]] = []

    for dest_idx, dest_key in enumerate(destination_keys):
        destination = content_records[dest_key]
        host_sentence_ids = stage1_candidates.get(dest_key, [])

        matches = _score_sentences_stage2(
            destination_embedding=dest_embeddings[dest_idx],
            sentence_ids=host_sentence_ids,
            sentence_ids_ordered=sentence_ids_ordered,
            sentence_embeddings=sentence_embeddings,
            sentence_records=sentence_records,
            top_k=STAGE2_TOP_K,
        )

        if not matches:
            diagnostics.append((dest_key[0], dest_key[1], "no_semantic_matches", None))
            continue

        blocked_reasons: set[str] = set()
        scored = score_destination_matches(
            destination,
            matches,
            content_records=content_records,
            sentence_records=sentence_records,
            existing_links=existing_links,
            learned_anchor_rows_by_destination=learned_anchor_rows_by_destination,
            rare_term_profiles=rare_term_profiles,
            weights=weights,
            march_2026_pagerank_bounds=march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=weighted_authority_settings["ranking_weight"],
            link_freshness_ranking_weight=link_freshness_settings["ranking_weight"],
            phrase_matching_settings=phrase_matching_settings,
            learned_anchor_settings=learned_anchor_settings,
            rare_term_settings=rare_term_settings,
            field_aware_settings=field_aware_settings,
            ga4_gsc_ranking_weight=ga4_gsc_settings["ranking_weight"],
            click_distance_ranking_weight=click_distance_settings["ranking_weight"],
            silo_settings=silo_settings,
            blocked_reasons=blocked_reasons,
        )

        if scored:
            if feedback_rerank_settings.enabled:
                scored = feedback_rerank_service.rerank_candidates(
                    scored,
                    host_scope_id_map={
                        c.host_content_id: content_records[(c.host_content_id, c.host_content_type)].scope_id
                        for c in scored
                    },
                    destination_scope_id_map={
                        destination.id: destination.scope_id
                    }
                )
            candidates_by_destination[dest_key] = scored
        elif "cross_silo_blocked" in blocked_reasons:
            diagnostics.append((
                dest_key[0],
                dest_key[1],
                "cross_silo_blocked",
                {
                    "mode": silo_settings.mode,
                    "destination_silo_group_id": destination.silo_group_id,
                    "destination_silo_group_name": destination.silo_group_name,
                },
            ))
        else:
            diagnostics.append((dest_key[0], dest_key[1], "all_candidates_filtered", None))

        if dest_idx % 100 == 0 and dest_idx > 0:
            pct = 0.50 + 0.35 * (dest_idx / items_in_scope)
            _progress(pct, f"Scored {dest_idx}/{items_in_scope} destinations...")

    del dest_embeddings, sentence_embeddings
    gc.collect()

    _progress(0.87, "Resolving host-reuse and circular-pair filters...")
    blocked_diagnostics: dict[ContentKey, str] = {}
    selected_candidates = select_final_candidates(
        candidates_by_destination,
        max_host_reuse=_get_max_host_reuse(),
        blocked_diagnostics=blocked_diagnostics,
    )
    for dest_key, reason in blocked_diagnostics.items():
        diagnostics.append((dest_key[0], dest_key[1], reason, None))

    _progress(0.92, "Persisting suggestions...")
    suggestions_created = _persist_suggestions(
        run_id=run_id,
        selected_candidates=selected_candidates,
        content_records=content_records,
        sentence_records=sentence_records,
        rerun_mode=rerun_mode,
    )

    _persist_diagnostics(run_id=run_id, diagnostics=diagnostics)

    _progress(1.0, f"Pipeline complete — {suggestions_created} suggestions created.")
    return PipelineResult(
        run_id=run_id,
        items_in_scope=items_in_scope,
        suggestions_created=suggestions_created,
        suggestions_skipped=items_in_scope - suggestions_created,
    )


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_weights() -> dict[str, float]:
    try:
        from apps.core.models import AppSetting
        qs = AppSetting.objects.filter(
            key__in=["w_semantic", "w_keyword", "w_node", "w_quality"]
        ).values_list("key", "value")
        overrides = {k: float(v) for k, v in qs}
        return {**DEFAULT_WEIGHTS, **overrides}
    except Exception:
        return dict(DEFAULT_WEIGHTS)


def _get_max_host_reuse() -> int:
    try:
        from apps.core.models import AppSetting
        setting = AppSetting.objects.filter(key="max_host_reuse").first()
        if setting:
            return int(setting.value)
    except Exception:
        pass
    return 3


def _load_silo_settings() -> SiloSettings:
    try:
        from apps.core.views import get_silo_settings

        config = get_silo_settings()
        return SiloSettings(
            mode=str(config.get("mode", "disabled")),
            same_silo_boost=float(config.get("same_silo_boost", 0.0)),
            cross_silo_penalty=float(config.get("cross_silo_penalty", 0.0)),
        )
    except Exception:
        return SiloSettings()


def _load_weighted_authority_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_weighted_authority_settings

        config = get_weighted_authority_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", 0.2)),
        }
    except Exception:
        return {
            "ranking_weight": 0.2,
        }


def _load_link_freshness_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_link_freshness_settings

        config = get_link_freshness_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", 0.0)),
        }
    except Exception:
        return {
            "ranking_weight": 0.0,
        }


def _load_phrase_matching_settings() -> PhraseMatchingSettings:
    try:
        from apps.core.views import get_phrase_matching_settings

        config = get_phrase_matching_settings()
        return PhraseMatchingSettings(
            ranking_weight=float(config.get("ranking_weight", 0.0)),
            enable_anchor_expansion=bool(config.get("enable_anchor_expansion", True)),
            enable_partial_matching=bool(config.get("enable_partial_matching", True)),
            context_window_tokens=int(config.get("context_window_tokens", 8)),
        )
    except Exception:
        return PhraseMatchingSettings()


def _load_learned_anchor_settings() -> LearnedAnchorSettings:
    try:
        from apps.core.views import get_learned_anchor_settings

        config = get_learned_anchor_settings()
        return LearnedAnchorSettings(
            ranking_weight=float(config.get("ranking_weight", 0.0)),
            minimum_anchor_sources=int(config.get("minimum_anchor_sources", 2)),
            minimum_family_support_share=float(config.get("minimum_family_support_share", 0.15)),
            enable_noise_filter=bool(config.get("enable_noise_filter", True)),
        )
    except Exception:
        return LearnedAnchorSettings()


def _load_rare_term_propagation_settings() -> RareTermPropagationSettings:
    try:
        from apps.core.views import get_rare_term_propagation_settings

        config = get_rare_term_propagation_settings()
        return RareTermPropagationSettings(
            enabled=bool(config.get("enabled", True)),
            ranking_weight=float(config.get("ranking_weight", 0.0)),
            max_document_frequency=int(config.get("max_document_frequency", 3)),
            minimum_supporting_related_pages=int(config.get("minimum_supporting_related_pages", 2)),
        )
    except Exception:
        return RareTermPropagationSettings()


def _load_field_aware_relevance_settings() -> FieldAwareRelevanceSettings:
    try:
        from apps.core.views import get_field_aware_relevance_settings

        config = get_field_aware_relevance_settings()
        return FieldAwareRelevanceSettings(
            ranking_weight=float(config.get("ranking_weight", 0.0)),
            title_field_weight=float(config.get("title_field_weight", 0.4)),
            body_field_weight=float(config.get("body_field_weight", 0.3)),
            scope_field_weight=float(config.get("scope_field_weight", 0.15)),
            learned_anchor_field_weight=float(config.get("learned_anchor_field_weight", 0.15)),
        )
    except Exception:
        return FieldAwareRelevanceSettings()


def _load_ga4_gsc_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_ga4_gsc_settings

        config = get_ga4_gsc_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", 0.05)),
        }
    except Exception:
        config_snapshot["algorithm_versions"]["rare_term_propagation"] = "v1"
        config_snapshot["algorithm_versions"]["click_distance"] = "v1"
        return {
            "ranking_weight": 0.05,
        }


def _load_click_distance_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_click_distance_settings

        config = get_click_distance_settings()
        return {
            "ranking_weight": float(config.get("ranking_weight", 0.0)),
        }
    except Exception:
        return {
            "ranking_weight": 0.0,
        }


def _load_feedback_rerank_settings() -> FeedbackRerankSettings:
    """Load feedback-driven explore/exploit settings from the DB."""
    try:
        from apps.core.views import get_feedback_rerank_settings
        raw = get_feedback_rerank_settings()
        return FeedbackRerankSettings(
            enabled=raw["enabled"],
            ranking_weight=raw["ranking_weight"],
            exploration_rate=raw["exploration_rate"],
        )
    except Exception:
        return FeedbackRerankSettings()


def _load_content_records(
    *,
    destination_scope_ids: set[int] | None = None,
    host_scope_ids: set[int] | None = None,
) -> dict[ContentKey, ContentRecord]:
    """Load all non-deleted content items with scope hierarchy via Django ORM."""
    from apps.content.models import ContentItem

    qs = ContentItem.objects.filter(is_deleted=False).select_related(
        "scope",
        "scope__parent",
        "scope__parent__parent",
        "scope__silo_group",
        "post",
    )

    if destination_scope_ids is not None or host_scope_ids is not None:
        scope_ids = set(destination_scope_ids or set()) | set(host_scope_ids or set())
        qs = qs.filter(scope_id__in=scope_ids)

    records: dict[ContentKey, ContentRecord] = {}
    for ci in qs:
        scope = ci.scope
        parent = scope.parent if scope else None
        grandparent = parent.parent if parent else None
        silo_group = scope.silo_group if scope else None

        primary_post_char_count = 0
        if hasattr(ci, "post") and ci.post:
            primary_post_char_count = ci.post.char_count or 0

        text = _destination_text(ci.title, ci.distilled_text or "")
        key: ContentKey = (ci.pk, ci.content_type)
        records[key] = ContentRecord(
            content_id=ci.pk,
            content_type=ci.content_type,
            title=ci.title or "",
            distilled_text=ci.distilled_text or "",
            scope_id=scope.pk if scope else 0,
            scope_type=scope.scope_type if scope else "",
            parent_id=parent.pk if parent else None,
            parent_type=parent.scope_type if parent else "",
            grandparent_id=grandparent.pk if grandparent else None,
            grandparent_type=grandparent.scope_type if grandparent else "",
            silo_group_id=silo_group.pk if silo_group else None,
            silo_group_name=silo_group.name if silo_group else "",
            reply_count=ci.reply_count or 0,
            march_2026_pagerank_score=float(ci.march_2026_pagerank_score or 0.0),
            link_freshness_score=float(ci.link_freshness_score or 0.5),
            content_value_score=float(ci.content_value_score or 0.5),
            click_distance_score=float(ci.click_distance_score or 0.5),
            primary_post_char_count=primary_post_char_count,
            tokens=tokenize_text(text),
            scope_title=scope.title if scope else "",
            parent_scope_title=parent.title if parent else "",
            grandparent_scope_title=grandparent.title if grandparent else "",
        )
    return records


def _load_sentence_records(
    content_keys: set[ContentKey],
) -> tuple[dict[int, SentenceRecord], dict[ContentKey, pr.BitMap]]:
    """Load sentence records for the given content keys using PyArrow for speed."""
    from apps.content.models import Sentence
    from django.db import connection

    content_pks = [pk for pk, _ in content_keys]
    
    # Use raw SQL + fetchall for maximum speed, then wrap in Arrow
    query = """
        SELECT s.id, s.content_item_id, ci.content_type, s.text, s.char_count
        FROM content_sentence s
        JOIN content_contentitem ci ON s.content_item_id = ci.id
        WHERE s.content_item_id = ANY(%s)
          AND ci.is_deleted = FALSE
          AND s.word_position <= %s
    """
    
    with connection.cursor() as cursor:
        cursor.execute(query, [content_pks, settings.HOST_SCAN_WORD_LIMIT])
        rows = cursor.fetchall()

    if not rows:
        return {}, {}

    # Convert to Arrow Table for metadata handling
    names = ["id", "content_id", "content_type", "text", "char_count"]
    table = pa.Table.from_batches([pa.RecordBatch.from_arrays(
        [pa.array([r[i] for r in rows]) for i in range(len(names))],
        names=names
    )])

    sentence_records: dict[int, SentenceRecord] = {}
    content_to_sentence_ids: dict[ContentKey, pr.BitMap] = defaultdict(pr.BitMap)

    for i in range(table.num_rows):
        sid = table["id"][i].as_py()
        cid = table["content_id"][i].as_py()
        ctype = table["content_type"][i].as_py()
        text = table["text"][i].as_py() or ""
        char_count = table["char_count"][i].as_py() or len(text)
        
        ckey: ContentKey = (cid, ctype)
        record = SentenceRecord(
            sentence_id=sid,
            content_id=cid,
            content_type=ctype,
            text=text,
            char_count=char_count,
            tokens=tokenize_text(text),
        )
        sentence_records[sid] = record
        content_to_sentence_ids[ckey].add(sid)

    return sentence_records, dict(content_to_sentence_ids)


def _load_existing_links() -> set[ExistingLinkKey]:
    from apps.graph.models import ExistingLink

    qs = ExistingLink.objects.values_list(
        "from_content_item__pk", "from_content_item__content_type",
        "to_content_item__pk", "to_content_item__content_type",
    )
    return {
        (
            (from_pk, from_type),
            (to_pk, to_type),
        )
        for from_pk, from_type, to_pk, to_type in qs
    }


def _load_learned_anchor_rows_by_destination() -> dict[ContentKey, list[LearnedAnchorInputRow]]:
    from apps.graph.models import ExistingLink

    rows_by_destination: dict[ContentKey, list[LearnedAnchorInputRow]] = defaultdict(list)
    for row in ExistingLink.objects.values(
        "to_content_item__pk",
        "to_content_item__content_type",
        "from_content_item_id",
        "anchor_text",
    ):
        destination_key: ContentKey = (
            row["to_content_item__pk"],
            row["to_content_item__content_type"],
        )
        rows_by_destination[destination_key].append(
            LearnedAnchorInputRow(
                source_content_id=int(row["from_content_item_id"]),
                anchor_text=row["anchor_text"] or "",
            )
        )
    return dict(rows_by_destination)


def _get_pending_destinations(rerun_mode: str) -> set[ContentKey]:
    if rerun_mode != "skip_pending":
        return set()

    from apps.suggestions.models import Suggestion
    qs = Suggestion.objects.filter(status="pending").values_list(
        "destination__pk", "destination__content_type"
    )
    return {(pk, ct) for pk, ct in qs}


def _supersede_pending_suggestions(destination_keys: list[ContentKey]) -> None:
    from apps.suggestions.models import Suggestion
    dest_pks = [pk for pk, _ in destination_keys]
    Suggestion.objects.filter(
        destination__pk__in=dest_pks,
        status="pending",
    ).update(status="superseded")


def _load_destination_embeddings(
    content_records: dict[ContentKey, ContentRecord],
    *,
    pending_destinations: set[ContentKey],
) -> tuple[tuple[ContentKey, ...], np.ndarray]:
    """Load L2-normalized destination embeddings from pgvector."""
    from apps.content.models import ContentItem

    candidate_keys = [
        key for key in content_records
        if key not in pending_destinations
    ]
    if not candidate_keys:
        return (), np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    pks = [pk for pk, _ in candidate_keys]
    qs = ContentItem.objects.filter(
        pk__in=pks,
        embedding__isnull=False,
    ).values_list("pk", "content_type", "embedding")

    found: dict[ContentKey, list[float]] = {}
    for pk, ct, emb in qs:
        if emb is not None:
            found[(pk, ct)] = emb

    valid_keys = [key for key in candidate_keys if key in found]
    if not valid_keys:
        return (), np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    matrix = np.array([found[key] for key in valid_keys], dtype=np.float32)
    return tuple(valid_keys), matrix


def _load_sentence_embeddings(
    content_keys: set[ContentKey],
) -> tuple[list[int], np.ndarray]:
    """Load sentence embeddings from pgvector using PyArrow for speed."""
    from apps.content.models import Sentence
    from django.db import connection

    content_pks = [pk for pk, _ in content_keys]
    query = """
        SELECT id, embedding
        FROM content_sentence
        WHERE content_item_id = ANY(%s)
          AND word_position <= %s
          AND embedding IS NOT NULL
        ORDER BY id
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [content_pks, settings.HOST_SCAN_WORD_LIMIT])
        rows = cursor.fetchall()

    if not rows:
        return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    ids = [r[0] for r in rows]
    vectors = np.array([r[1] for r in rows], dtype=np.float32)
    return ids, vectors


# ---------------------------------------------------------------------------
# Stage 1 — coarse content-level candidate retrieval
# ---------------------------------------------------------------------------

def _stage1_candidates(
    *,
    destination_keys: tuple[ContentKey, ...],
    dest_embeddings: np.ndarray,
    content_records: dict[ContentKey, ContentRecord],
    content_to_sentence_ids: dict[ContentKey, list[int]],
    top_k: int,
    block_size: int,
) -> dict[ContentKey, list[int]]:
    """Stage 1: find top-K host content items per destination via cosine similarity.

    Returns a mapping from destination_key -> flat list of candidate sentence IDs
    (all sentences from the top-K host content items).
    """
    # Build a host embedding matrix from content items that have sentence embeddings
    host_keys = [
        key for key in content_records
        if key in content_to_sentence_ids and content_to_sentence_ids[key]
    ]
    if not host_keys:
        return {}

    from apps.content.models import ContentItem
    host_pks = [pk for pk, _ in host_keys]
    host_emb_qs = ContentItem.objects.filter(
        pk__in=host_pks,
        embedding__isnull=False,
    ).values_list("pk", "content_type", "embedding")

    host_emb_map: dict[ContentKey, list[float]] = {
        (pk, ct): emb for pk, ct, emb in host_emb_qs if emb is not None
    }
    valid_host_keys = [k for k in host_keys if k in host_emb_map]
    if not valid_host_keys:
        return {}

    host_matrix = np.array(
        [host_emb_map[k] for k in valid_host_keys], dtype=np.float32
    )

    result: dict[ContentKey, list[int]] = {}
    n_dest = len(destination_keys)

    for block_start in range(0, n_dest, block_size):
        block_end = min(block_start + block_size, n_dest)
        dest_block = dest_embeddings[block_start:block_end]
        dest_keys_block = destination_keys[block_start:block_end]

        # cosine similarity: dest_block (B, D) @ host_matrix.T (D, H) -> (B, H)
        sims = dest_block @ host_matrix.T

        for b_idx, dest_key in enumerate(dest_keys_block):
            row = sims[b_idx]
            # Get top-K host indices (excluding self)
            top_indices = np.argpartition(row, -min(top_k, len(valid_host_keys)))[-top_k:]
            top_indices = top_indices[np.argsort(-row[top_indices])]

            sentence_ids: list[int] = []
            for h_idx in top_indices:
                host_key = valid_host_keys[h_idx]
                if host_key == dest_key:
                    continue
                sentence_ids.extend(content_to_sentence_ids.get(host_key, []))

            if sentence_ids:
                result[dest_key] = sentence_ids

    return result


# ---------------------------------------------------------------------------
# Stage 2 — sentence-level scoring
# ---------------------------------------------------------------------------

def _score_sentences_stage2(
    *,
    destination_embedding: np.ndarray,
    sentence_ids: list[int],
    sentence_ids_ordered: list[int],
    sentence_embeddings: np.ndarray,
    sentence_records: dict[int, SentenceRecord],
    top_k: int,
) -> list[SentenceSemanticMatch]:
    """Stage 2: score candidate sentences by cosine similarity to destination."""
    if not sentence_ids:
        return []

    # Build an index from sentence_id to row index in sentence_embeddings
    id_to_row = {sid: idx for idx, sid in enumerate(sentence_ids_ordered)}

    candidate_rows: list[int] = []
    candidate_ids: list[int] = []
    for sid in sentence_ids:
        row = id_to_row.get(sid)
        if row is not None:
            candidate_rows.append(row)
            candidate_ids.append(sid)

    if not candidate_rows:
        return []

    candidate_matrix = sentence_embeddings[candidate_rows]
    scores = candidate_matrix @ destination_embedding  # cosine similarity (normalized)

    # Keep top-K
    k = min(top_k, len(scores))
    top_idx = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx[np.argsort(-scores[top_idx])]

    matches: list[SentenceSemanticMatch] = []
    for i in top_idx:
        sid = candidate_ids[i]
        record = sentence_records.get(sid)
        if record is None:
            continue
        matches.append(SentenceSemanticMatch(
            host_content_id=record.content_id,
            host_content_type=record.content_type,
            sentence_id=sid,
            score_semantic=float(scores[i]),
        ))

    return matches


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

    created = 0
    for candidate in selected_candidates:
        dest_key = candidate.destination_key
        dest_record = content_records.get(dest_key)
        sentence_record = sentence_records.get(candidate.host_sentence_id)
        if dest_record is None or sentence_record is None:
            continue

        try:
            dest_ci = ContentItem.objects.get(pk=candidate.destination_content_id)
            host_ci = ContentItem.objects.get(pk=candidate.host_content_id)
            host_sentence = Sentence.objects.get(pk=candidate.host_sentence_id)
        except (ContentItem.DoesNotExist, Sentence.DoesNotExist):
            continue

        if rerun_mode == "full_regenerate":
            Suggestion.objects.filter(
                destination=dest_ci,
                status__in=["pending", "superseded"],
            ).delete()

        Suggestion.objects.create(
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
            phrase_match_diagnostics=candidate.phrase_match_diagnostics,
            learned_anchor_diagnostics=candidate.learned_anchor_diagnostics,
            rare_term_diagnostics=candidate.rare_term_diagnostics,
            field_aware_diagnostics=candidate.field_aware_diagnostics,
            score_final=candidate.score_final,
            status="pending",
        )
        created += 1

    if run:
        run.suggestions_created = created
        run.destinations_processed = len(selected_candidates)
        run.save(update_fields=["suggestions_created", "destinations_processed", "updated_at"])

    return created


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

    to_create = []
    for content_id, content_type, reason, detail in diagnostics:
        try:
            ci = ContentItem.objects.get(pk=content_id, content_type=content_type)
        except ContentItem.DoesNotExist:
            continue
        to_create.append(PipelineDiagnostic(
            pipeline_run=run,
            destination=ci,
            skip_reason=reason,
            detail=detail or {},
        ))

    if to_create:
        PipelineDiagnostic.objects.bulk_create(to_create, ignore_conflicts=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _destination_text(title: str, distilled_text: str) -> str:
    title_clean = (title or "").strip()
    distilled_clean = (distilled_text or "").strip()
    if distilled_clean:
        return f"{title_clean}\n\n{distilled_clean}".strip()
    return title_clean


try:
    from .embeddings import EMBEDDING_DIM
except ImportError:
    EMBEDDING_DIM = 1024
