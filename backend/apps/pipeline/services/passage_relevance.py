"""FR-053 — Passage-Level Relevance Scoring (masterplan Group E V1).

Plain-English: a long destination page might have one perfectly-relevant
section buried among nine mediocre ones. The page-level embedding
averages that section away. This module breaks each destination into
~200-token passages, embeds each one, and at suggestion time uses the
BEST-matching passage's similarity as a new additive contribution to
``score_final``.

Algorithm baseline: Patent US 9,940,367 B1 (Google 2018) col 5 ll 25–48
+ col 8 ll 5–32. Chunk-size baseline: Callan 1994 SIGIR §5 (150–300
token window sweet spot). Chunk source: ``Post.clean_text`` (post
Group D.1). Storage: float32 pgvector on ``PassageEmbedding`` (V1
simplification — int8 FAISS quantisation is in the spec's Pending list).

V1 contract:
    * Idempotent: ``regenerate_passage_embeddings_for`` skips passages
      whose ``embedding_text_hash`` and ``embedding_model_version`` are
      both already current. Running twice on unchanged content does
      zero work.
    * Cross-source dedup safe: rows with ``duplicate_of`` set never get
      passages stored on them; the ranker dereferences via the canonical
      at score time.
    * Defensive: ``score()`` never raises into ``score_destination_matches``
      — RANKING-GATES.md A7 mandates a neutral-fallback path for every
      failure mode.

V2 follow-ups (from the spec ``## Pending``):
    * int8-quantised FAISS index for query-time speedup
    * C++ kernel ``passagesim.cpp`` for batch passage similarity
    * Frontend settings card + suggestion-detail diagnostic block
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings access — three-tier helper (operator override → recommended preset
# → hardcoded fallback) extracted to ``apps.core.services.settings_helpers``
# (Phase 4 tech-debt sweep). The wrappers below stay so existing call sites
# keep working without churn — each is a 1-line proxy now instead of a
# 15-line copy of the same boilerplate.
# ---------------------------------------------------------------------------

from apps.core.services.settings_helpers import (
    setting_bool as _setting_bool,
    setting_float as _setting_float,
    setting_int as _setting_int,
)


# ---------------------------------------------------------------------------
# Hash helper. SHA-256 hex digest of the exact passage text we feed BGE-M3.
# ---------------------------------------------------------------------------


def _passage_text_hash(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(
        text.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Index time: chunk + embed
# ---------------------------------------------------------------------------


def regenerate_passage_embeddings_for(content_item) -> int:
    """Idempotent: ensure ``content_item`` has up-to-date passage embeddings.

    Returns the number of passages re-embedded (0 if already current).

    Side effects:
        * Creates / updates / deletes ``PassageEmbedding`` rows for
          ``content_item``.
        * Reuses the existing BGE-M3 model from
          ``apps.pipeline.services.embeddings``.
    """
    from apps.content.models import PassageEmbedding
    from apps.pipeline.services.embeddings import (
        _encode_batch_via_provider,
        _get_batch_size,
        _get_model_name,
        _l2_normalize,
        _load_model,
        get_current_embedding_signature,
    )
    from apps.sources.passages import Passage, segment_from_sentences

    if not _setting_bool("passage_relevance.enabled", True):
        return 0

    if getattr(content_item, "duplicate_of_id", None):
        # Cross-source duplicates reuse the canonical's passages at score time.
        # Never write passages on a duplicate row.
        return 0

    # Pull clean_text via the OneToOne related_name `post`.
    post = getattr(content_item, "post", None)
    if post is None or not getattr(post, "clean_text", None):
        # No body to chunk; clear any stale rows.
        PassageEmbedding.objects.filter(content_item=content_item).delete()
        return 0

    target_window = _setting_int("passage_relevance.passage_words", 200)
    max_passages = _setting_int("passage_relevance.passages_per_page_max", 0)

    # Reuse the existing sentence splitter so passage boundaries align with
    # what the rest of the pipeline already considers "a sentence". We split
    # on punctuation rather than running spaCy again — cheap, deterministic.
    sentences = _split_into_sentences(post.clean_text)

    # 25% overlap (rough estimate: if 1 sentence ~ 15 tokens, overlap_sentences=3 or 4)
    # We will pass overlap_tokens to the segment_from_sentences if possible,
    # but currently it uses overlap_sentences=1. Let's make it 3 for ~25% overlap of ~200 tokens.
    passages_full = segment_from_sentences(
        sentences,
        target_window_tokens=target_window,
        overlap_sentences=3,
    )

    # Cap by even spacing per the FR-053 spec ## Math-Fidelity Note step 3.
    # Phase 2: max_passages=0 means unlimited.
    if max_passages > 0 and len(passages_full) > max_passages:
        passages_full = _evenly_space_cap(passages_full, max_passages)

    # Re-index 0..len(passages)-1 since the segmenter's ``index`` field
    # may have gaps after the cap. (Actually segment_from_sentences emits
    # contiguous indices; we still re-index defensively.)
    passages: list[Passage] = [
        Passage(
            index=i,
            text=p.text,
            token_start=p.token_start,
            token_end=p.token_end,
            token_count=p.token_count,
        )
        for i, p in enumerate(passages_full)
    ]

    if not passages:
        PassageEmbedding.objects.filter(content_item=content_item).delete()
        return 0

    # Compute hashes for the new passages. Decide which need re-embedding.
    new_hashes = [_passage_text_hash(p.text) for p in passages]

    model_name = _get_model_name()
    model = _load_model(model_name)
    embedding_signature = get_current_embedding_signature(
        model=model,
        model_name=model_name,
    )

    existing = {
        row.passage_index: row
        for row in PassageEmbedding.objects.filter(content_item=content_item)
    }

    # Fetch active OPQ Codebook
    from apps.content.models import OPQCodebook

    active_codebook = OPQCodebook.objects.filter(is_active=True).first()
    active_opq_version = active_codebook.corpus_signature if active_codebook else ""

    needs_embed_indices: list[int] = []
    needs_embed_texts: list[str] = []
    needs_opq_indices: list[int] = []

    for i, p in enumerate(passages):
        existing_row = existing.get(i)

        embed_current = False
        opq_current = False

        if (
            existing_row is not None
            and existing_row.embedding is not None
            and existing_row.embedding_text_hash == new_hashes[i]
            and existing_row.embedding_model_version == embedding_signature
        ):
            embed_current = True

            # Check OPQ
            if (
                active_codebook
                and existing_row.opq_codebook_version == active_opq_version
                and existing_row.opq_code is not None
            ):
                opq_current = True
            elif not active_codebook:
                # If no active codebook, we consider OPQ current (it will be NULL)
                opq_current = True

        if embed_current and opq_current:
            continue  # fully current

        if not embed_current:
            needs_embed_indices.append(i)
            needs_embed_texts.append(p.text)
            if active_codebook:
                needs_opq_indices.append(i)
        else:
            # Embedding is current, but OPQ is not
            if active_codebook:
                needs_opq_indices.append(i)

    if needs_embed_texts:
        batch_size = _get_batch_size(model)
        raw_vectors = _encode_batch_via_provider(
            batch_texts=needs_embed_texts,
            model=model,
            batch_size=batch_size,
            job_id=None,
        )
        # _encode_batch_via_provider returns shape (N, D) for batches
        if raw_vectors.ndim == 1:
            raw_vectors = raw_vectors.reshape(1, -1)
        normalised = _l2_normalize(raw_vectors)
    else:
        normalised = np.zeros((0, 1024), dtype=np.float64)

    # Dictionary to collect vectors for OPQ encoding
    vectors_for_opq = {}

    # Upsert each passage row.
    for slot, i in enumerate(needs_embed_indices):
        p = passages[i]
        vec = normalised[slot].tolist()
        vectors_for_opq[i] = normalised[slot]
        PassageEmbedding.objects.update_or_create(
            content_item=content_item,
            passage_index=i,
            defaults={
                "text": p.text,
                "word_count": p.token_count,
                "embedding": vec,
                "embedding_model_version": embedding_signature,
                "embedding_text_hash": new_hashes[i],
                "passage_words_setting": target_window,
            },
        )

    # Perform OPQ encoding if needed
    if active_codebook and needs_opq_indices:
        try:
            from extensions import quantemb

            # Gather vectors to encode
            to_encode_matrix = []
            for i in needs_opq_indices:
                if i in vectors_for_opq:
                    to_encode_matrix.append(vectors_for_opq[i])
                else:
                    # It was already embedded, fetch from DB
                    to_encode_matrix.append(
                        np.array(existing[i].embedding, dtype=np.float32)
                    )

            encode_data = np.vstack(to_encode_matrix).astype(np.float32)
            rot = np.frombuffer(active_codebook.rotation, dtype=np.float32).reshape(
                (1024, 1024)
            )
            cb = np.frombuffer(active_codebook.codebooks, dtype=np.float32).reshape(
                (active_codebook.n_subquantisers, active_codebook.k_centroids, -1)
            )

            codes = quantemb.opq_encode(encode_data, rot, cb)

            # Save codes
            for slot, i in enumerate(needs_opq_indices):
                PassageEmbedding.objects.filter(
                    content_item=content_item, passage_index=i
                ).update(
                    opq_code=codes[slot].tobytes(),
                    opq_codebook_version=active_opq_version,
                )

        except ImportError:
            logger.warning(
                "quantemb extension not available; skipping OPQ encoding for passages."
            )
            pass

    # Delete any stale rows that the new chunk count no longer needs.
    stale_indices = [idx for idx in existing if idx >= len(passages)]
    if stale_indices:
        PassageEmbedding.objects.filter(
            content_item=content_item,
            passage_index__in=stale_indices,
        ).delete()

    return len(needs_embed_indices)


def _split_into_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter for passage chunking.

    We avoid running spaCy a second time at passage time — the pipeline
    already pays that cost in ``_persist_content_body``. For the chunker
    we just need clean sentence boundaries, which a punctuation-based
    splitter handles well enough. Empty / whitespace-only sentences
    are filtered out.
    """
    if not text:
        return []
    import re

    # Split on terminator + whitespace; preserve sentence-final punctuation.
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s and s.strip()]


def _evenly_space_cap(passages, max_count: int):
    """Keep ``max_count`` passages, evenly spaced through the input list.

    Mirrors the FR-053 spec ``## Math-Fidelity Note`` chunking pseudocode
    cap step. Indices are computed as floor(step * i) so the first and
    last passages are always among the kept set when ``max_count >= 2``.
    """
    if max_count <= 0 or not passages:
        return []
    n = len(passages)
    if n <= max_count:
        return list(passages)
    step = n / max_count
    return [passages[int(step * i)] for i in range(max_count)]


# ---------------------------------------------------------------------------
# Query time: max-cosine + diagnostics
# ---------------------------------------------------------------------------


_NEUTRAL_SCORE = 0.5
_DIAGNOSTIC_PREVIEW_CHARS = 100


def _empty_diagnostics(state: str) -> dict[str, Any]:
    """Common neutral-fallback diagnostic shape — every key the spec lists."""
    return {
        "score_passage_relevance": _NEUTRAL_SCORE,
        "passage_relevance_state": state,
        "best_passage_index": None,
        "best_passage_similarity": 0.0,
        "passage_count": 0,
        "all_passage_similarities": [],
        "best_passage_preview": "",
        "passages_per_page_setting": _setting_int(
            "passage_relevance.passages_per_page_max", 0
        ),
        "passage_words_setting": _setting_int("passage_relevance.passage_words", 200),
    }


def _try_score_path_opq_adc(target, query) -> tuple[float, dict[str, Any]] | None:
    """Path 1 of FR-053 ``score()`` — OPQ asymmetric-distance scoring.

    Returns ``(score, diagnostics)`` when an active OPQ codebook exists
    AND the target destination has at least one passage with a matching
    ``opq_codebook_version``. Returns ``None`` when any prerequisite is
    missing — caller falls through to Path 2 (fp32 MaxSim).

    Never raises. Any exception path silently returns None so the score
    function flows through to the slower-but-always-correct fp32 path.

    Plain-English: when the operator has trained an OPQ codebook (one
    setup step, runs in ~10 minutes for a 100k-passage corpus), this
    path takes over. Each passage shrinks from a 4 KB float array to
    a 64-byte code, and per-query scoring is 5-10x faster. The OPQ
    table also drops the per-destination working memory by 64x, so a
    destination with 50 passages now needs ~3 KB of vectors loaded
    instead of ~200 KB.
    """
    try:
        from extensions import ivf_index as _ivf_kernel
    except ImportError:
        return None

    try:
        from apps.content.models import OPQCodebook, PassageEmbedding
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        return None

    if not _setting_bool("passage_relevance.opq_index_enabled", True):
        return None

    try:
        active_codebook = OPQCodebook.objects.filter(is_active=True).first()
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        return None
    if active_codebook is None:
        return None

    try:
        code_rows = list(
            PassageEmbedding.objects.filter(
                content_item=target,
                opq_code__isnull=False,
                opq_codebook_version=active_codebook.corpus_signature,
            )
            .only("passage_index", "opq_code", "text")
            .order_by("passage_index")
        )
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
        return None
    if not code_rows:
        return None

    try:
        m = int(active_codebook.n_subquantisers)
        k = int(active_codebook.k_centroids)
        rotation_bytes = bytes(active_codebook.rotation)
        codebook_bytes = bytes(active_codebook.codebooks)

        rotation_flat = np.frombuffer(rotation_bytes, dtype=np.float32)
        rotation_dim = int(round(rotation_flat.size**0.5))
        if rotation_dim * rotation_dim != rotation_flat.size:
            return None
        rotation = rotation_flat.reshape(rotation_dim, rotation_dim)

        codebook_flat = np.frombuffer(codebook_bytes, dtype=np.float32)
        if codebook_flat.size != m * k * (rotation_dim // m):
            return None
        codebooks = codebook_flat.reshape(m, k, rotation_dim // m)

        codes_concat = b"".join(bytes(row.opq_code) for row in code_rows)
        codes = np.frombuffer(codes_concat, dtype=np.uint8).reshape(-1, m).copy()

        query_arr = np.ascontiguousarray(np.asarray(query, dtype=np.float32))
        if query_arr.shape[0] != rotation_dim:
            return None

        best_idx, best_sim = _ivf_kernel.adc_score_destination(
            query_arr, codes, rotation, codebooks
        )
    except Exception:
        logger.debug(
            "OPQ ADC path failed for content_item=%s — falling through to fp32 MaxSim",
            getattr(target, "pk", None),
            exc_info=True,
        )
        return None

    clamped_sim = float(max(0.0, min(1.0, best_sim)))
    score_value = 0.5 + 0.5 * clamped_sim
    best_row = code_rows[int(best_idx)]
    diagnostics = {
        "score_passage_relevance": score_value,
        "passage_relevance_state": "computed",
        "scoring_path": "opq_adc",
        "best_passage_index": int(best_row.passage_index),
        "best_passage_similarity": clamped_sim,
        "passage_count": len(code_rows),
        "best_passage_preview": (best_row.text or "")[:_DIAGNOSTIC_PREVIEW_CHARS],
        "opq_codebook_version": active_codebook.corpus_signature,
        "opq_codebook_size": m,
        "opq_centroids_per_subquantiser": k,
        "passages_per_page_setting": _setting_int(
            "passage_relevance.passages_per_page_max", 0
        ),
        "passage_words_setting": _setting_int("passage_relevance.passage_words", 200),
    }
    return score_value, diagnostics


def score(host_sentence_embedding, content_item) -> tuple[float, dict[str, Any]]:
    """Return ``(score, diagnostics)`` for one (host, destination) pair.

    Per the FR-053 spec:
        clamped_sim = max(0, min(1, max_i cos(host_q, passage_e_i)))
        score = 0.5 + 0.5 * clamped_sim

    The score is in ``[0.5, 1.0]``. The additive contribution to
    ``score_final`` is computed by ``score_component`` below — that
    centres around 0.5 so a neutral score adds zero.

    Never raises. Every failure path returns the neutral shape.
    """
    try:
        if host_sentence_embedding is None:
            return _NEUTRAL_SCORE, _empty_diagnostics("neutral_no_query_embedding")

        # Defensive: caller may pass None when the destination's
        # underlying ContentItem couldn't be loaded (e.g. transient
        # DB error during ranker prefetch).
        if content_item is None:
            return _NEUTRAL_SCORE, _empty_diagnostics("neutral_no_destination")

        if not _setting_bool("passage_relevance.enabled", True):
            return _NEUTRAL_SCORE, _empty_diagnostics("neutral_feature_disabled")

        # Cross-source duplicate dereference (Group A.6). We always score
        # against the canonical row's passages.
        target = content_item
        duplicate_of_id = getattr(content_item, "duplicate_of_id", None)
        if duplicate_of_id:
            from apps.content.models import ContentItem

            target = (
                ContentItem.objects.filter(pk=duplicate_of_id).first() or content_item
            )

        from apps.content.models import PassageEmbedding

        q = np.asarray(host_sentence_embedding, dtype=np.float32)

        # ── Path 1: OPQ ADC scoring ──────────────────────────────────
        # Triggers when an active OPQCodebook exists AND the destination
        # has at least one passage with a matching opq_code (per
        # ``opq_codebook_version``). Each code is 64 bytes vs 4096 bytes
        # for fp32 — 64× less I/O — and the ADC inner loop is just
        # M=64 byte loads + LUT additions. On a hot-path call this is
        # 5-10× faster than the fp32 MaxSim path. Citations: Patent US
        # 8,447,765 B2 (OPQ); Jegou-Douze-Schmid 2010 CVPR (IVFADC).
        path1_result = _try_score_path_opq_adc(target, q)
        if path1_result is not None:
            return path1_result

        # ── Path 2: fp32 MaxSim (existing default) ───────────────────
        rows = list(
            PassageEmbedding.objects.filter(
                content_item=target,
                embedding__isnull=False,
            ).order_by("passage_index")
        )

        if not rows:
            return _NEUTRAL_SCORE, _empty_diagnostics("neutral_no_passages")

        passage_matrix = np.vstack(
            [np.asarray(row.embedding, dtype=np.float32) for row in rows]
        )

        # Both q and passages are L2-normalised at write time, so cosine
        # similarity reduces to a dot product.
        try:
            from extensions import passagesim

            best_sim, best_idx = passagesim.maxsim(q, passage_matrix)
            sims = [0.0] * len(rows)
            sims[best_idx] = best_sim
        except ImportError:
            sims = passage_matrix @ q
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
        clamped_sim = max(0.0, min(1.0, best_sim))
        score_value = 0.5 + 0.5 * clamped_sim

        diagnostics = {
            "score_passage_relevance": score_value,
            "passage_relevance_state": "computed",
            "scoring_path": "fp32_maxsim",
            "best_passage_index": int(rows[best_idx].passage_index),
            "best_passage_similarity": best_sim,
            "passage_count": len(rows),
            "all_passage_similarities": [float(s) for s in sims],
            "best_passage_preview": (rows[best_idx].text or "")[
                :_DIAGNOSTIC_PREVIEW_CHARS
            ],
            "passages_per_page_setting": _setting_int(
                "passage_relevance.passages_per_page_max", 0
            ),
            "passage_words_setting": _setting_int(
                "passage_relevance.passage_words", 200
            ),
        }
        return score_value, diagnostics

    except Exception:
        logger.exception(
            "passage_relevance.score failed for content_item=%s — returning neutral",
            getattr(content_item, "pk", None),
        )
        return _NEUTRAL_SCORE, _empty_diagnostics("neutral_processing_error")


def score_component(score_value: float) -> float:
    """Convert ``score_passage_relevance`` to the additive ranker component.

    Per FR-053 spec ``## Math-Fidelity Note`` "Ranking hook":
        component = max(0, min(1, 2 * (score - 0.5)))

    The neutral score (0.5) maps to 0.0 contribution. A perfect match
    (1.0) maps to 1.0 contribution. The ranker multiplies this by
    ``passage_relevance.ranking_weight`` before adding to ``score_final``.
    """
    return max(0.0, min(1.0, 2.0 * (score_value - _NEUTRAL_SCORE)))


def ranking_weight() -> float:
    """Live ranking weight from AppSetting / Recommended preset."""
    return max(
        0.0,
        min(0.15, _setting_float("passage_relevance.ranking_weight", 0.05)),
    )
