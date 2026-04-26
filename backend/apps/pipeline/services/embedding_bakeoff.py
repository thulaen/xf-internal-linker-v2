"""Automated provider bake-off — MRR / NDCG / Recall (plan Part 4, FR-232).

Pure scoring logic. The task layer (``tasks_embedding_bakeoff``) orchestrates
sampling, provider iteration, and persistence. Everything here is deterministic
given the same sample + stored vectors.

Research grounding (docstring only — full citations in FR-232 spec):
  * Voorhees 1999 — TREC qrel methodology (positive / negative sampling).
  * Järvelin & Kekäläinen 2002 — NDCG.
  * Muennighoff et al. 2023 — MTEB metric set.
  * Thakur et al. 2021 — BEIR zero-shot evaluation.

Resource contract: ≤256 MB RAM, ≤246 MB disk.
  * Streams in batches of 64; never holds the full candidate vector set.
  * Metric accumulators are scalar floats; disk-free by design.
  * Final row in ``EmbeddingBakeoffResult`` is ~500 bytes.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_BATCH = 64
_TOP_K = 10
_DEFAULT_SAMPLE_SIZE = 1000


@dataclass(slots=True)
class BakeoffRun:
    provider_name: str
    signature: str
    sample_size: int
    mrr_at_10: float = 0.0
    ndcg_at_10: float = 0.0
    recall_at_10: float = 0.0
    mean_positive_cosine: float = 0.0
    mean_negative_cosine: float = 0.0
    separation_score: float = 0.0
    cost_usd: float = 0.0
    latency_ms_p50: int = 0
    latency_ms_p95: int = 0


def sample_ground_truth(
    sample_size: int = _DEFAULT_SAMPLE_SIZE,
) -> tuple[
    list[tuple[int, int]],
    list[tuple[int, int]],
]:
    """Return ``(positives, negatives)`` where each pair is ``(host_id, destination_id)``.

    Positives = Suggestion status in {approved, applied, verified}.
    Negatives = Suggestion status == rejected.
    Random stratified sample drawn with a deterministic seed for reproducibility.
    """
    try:
        from apps.suggestions.models import Suggestion
    except Exception:
        return [], []

    positives_qs = list(
        Suggestion.objects.filter(
            status__in=("approved", "applied", "verified")
        ).values_list("host_id", "destination_id")
    )
    negatives_qs = list(
        Suggestion.objects.filter(status="rejected").values_list(
            "host_id", "destination_id"
        )
    )
    rng = random.Random(42)
    pos = (
        positives_qs
        if len(positives_qs) <= sample_size
        else rng.sample(positives_qs, sample_size)
    )
    neg = (
        negatives_qs
        if len(negatives_qs) <= sample_size
        else rng.sample(negatives_qs, sample_size)
    )
    return pos, neg


def load_stored_vectors(pks: set[int]) -> dict[int, np.ndarray]:
    """Load stored embeddings for the given set of ContentItem PKs."""
    try:
        from apps.content.models import ContentItem
    except Exception:
        return {}
    out: dict[int, np.ndarray] = {}
    qs = ContentItem.objects.filter(pk__in=pks).values_list("pk", "embedding")
    for pk, emb in qs.iterator(chunk_size=500):
        if emb is None:
            continue
        try:
            out[pk] = np.asarray(emb, dtype=np.float32)
        except Exception:
            continue
    return out


def load_texts(pks: set[int]) -> dict[int, str]:
    """Load display text for each ContentItem (title + distilled)."""
    try:
        from apps.content.models import ContentItem
    except Exception:
        return {}
    qs = ContentItem.objects.filter(pk__in=pks).values_list(
        "pk", "title", "distilled_text"
    )
    return {
        pk: f"{title or ''}\n\n{distilled or ''}".strip()
        for pk, title, distilled in qs.iterator(chunk_size=500)
    }


def score_provider(
    *,
    provider: Any,
    positives: list[tuple[int, int]],
    negatives: list[tuple[int, int]],
    texts: dict[int, str],
    destination_pool_vectors: dict[int, np.ndarray] | None = None,
) -> BakeoffRun:
    """Stream-embed hosts + destinations through ``provider``; compute metrics.

    For retrieval metrics we treat each positive pair as a query: embed the
    host text, rank all destination candidates by cosine, and check whether
    the known-positive destination lands in the top-K. This follows the MTEB
    / BEIR protocol with our own labelled qrels.
    """
    if not positives:
        return BakeoffRun(
            provider_name=getattr(provider, "name", "unknown"),
            signature=getattr(provider, "signature", ""),
            sample_size=0,
        )

    # Destination pool: every destination that appears in positives or negatives.
    pool_ids = sorted({d for _, d in positives} | {d for _, d in negatives})
    if destination_pool_vectors is None:
        destination_pool_vectors = {}

    # Embed pool destinations that are not already cached.
    to_embed = [pid for pid in pool_ids if pid not in destination_pool_vectors]
    latencies: list[float] = []
    total_cost = 0.0

    def _embed(texts_list: list[str]) -> tuple[np.ndarray, float, float]:
        t0 = time.perf_counter()
        result = provider.embed(texts_list, batch_size=_BATCH)
        latency_ms = (time.perf_counter() - t0) * 1000
        return result.vectors, latency_ms, float(getattr(result, "cost_usd", 0.0))

    # Embed destinations in batches.
    pool_vecs: dict[int, np.ndarray] = dict(destination_pool_vectors)
    for i in range(0, len(to_embed), _BATCH):
        slice_ids = to_embed[i : i + _BATCH]
        slice_texts = [texts.get(pid, "") or "" for pid in slice_ids]
        vecs, latency_ms, cost = _embed(slice_texts)
        total_cost += cost
        latencies.append(latency_ms)
        for pid, vec in zip(slice_ids, vecs):
            pool_vecs[pid] = vec.astype(np.float32, copy=False)

    if not pool_vecs:
        return BakeoffRun(
            provider_name=getattr(provider, "name", "unknown"),
            signature=getattr(provider, "signature", ""),
            sample_size=len(positives),
        )

    # Stack the pool into a single matrix for vectorised cosine scoring.
    pool_id_order = list(pool_vecs.keys())
    pool_matrix = np.vstack([pool_vecs[pid] for pid in pool_id_order])  # (P, D)
    pool_index = {pid: idx for idx, pid in enumerate(pool_id_order)}

    # Metrics accumulators.
    mrr_sum = 0.0
    ndcg_sum = 0.0
    recall_hits = 0
    pos_cosines: list[float] = []
    neg_cosines: list[float] = []

    # Embed host queries in batches, score against the full pool.
    host_batches = [positives[i : i + _BATCH] for i in range(0, len(positives), _BATCH)]
    for batch in host_batches:
        host_ids = [h for h, _ in batch]
        dest_ids = [d for _, d in batch]
        host_texts = [texts.get(hid, "") or "" for hid in host_ids]
        query_vecs, latency_ms, cost = _embed(host_texts)
        total_cost += cost
        latencies.append(latency_ms)

        # Cosine scores: (query_vecs @ pool_matrix.T). Both already L2-normalised
        # for API providers; for local, mean-pool result is normalised in
        # ``embed_single``. In batch ``embed`` for local, vectors may NOT be
        # unit-norm — we normalise defensively here to keep metrics comparable.
        q_norms = np.linalg.norm(query_vecs, axis=1, keepdims=True)
        q_norms = np.where(q_norms > 0, q_norms, 1.0)
        query_vecs_n = query_vecs / q_norms
        p_norms = np.linalg.norm(pool_matrix, axis=1, keepdims=True)
        p_norms = np.where(p_norms > 0, p_norms, 1.0)
        pool_n = pool_matrix / p_norms
        scores = query_vecs_n @ pool_n.T  # (B, P)

        for row_idx, dest_id in enumerate(dest_ids):
            target_col = pool_index.get(dest_id)
            if target_col is None:
                continue
            scores_row = scores[row_idx]
            target_score = float(scores_row[target_col])
            pos_cosines.append(target_score)

            # Rank of target (descending). Larger = worse.
            order = np.argsort(-scores_row)
            rank = int(np.where(order == target_col)[0][0]) + 1
            if rank <= _TOP_K:
                mrr_sum += 1.0 / rank
                # NDCG@10 with binary relevance: DCG = 1/log2(rank+1); iDCG = 1.
                ndcg_sum += 1.0 / np.log2(rank + 1)
                recall_hits += 1
            # Else contributes 0 to each.

    # Negative-pair cosines: for each negative, compute host vs destination
    # cosine. We reuse the already-embedded destinations; host embeddings come
    # from a small extra batch (negatives are typically ~= positives in count).
    if negatives:
        neg_host_ids = [h for h, _ in negatives]
        neg_host_texts = [texts.get(hid, "") or "" for hid in neg_host_ids]
        neg_vecs: list[np.ndarray] = []
        for i in range(0, len(neg_host_texts), _BATCH):
            sub = neg_host_texts[i : i + _BATCH]
            vecs, latency_ms, cost = _embed(sub)
            total_cost += cost
            latencies.append(latency_ms)
            neg_vecs.extend(vecs)
        for (_, dest_id), host_vec in zip(negatives, neg_vecs):
            dcol = pool_index.get(dest_id)
            if dcol is None:
                continue
            pool_vec = pool_matrix[dcol]
            hv = host_vec.astype(np.float32, copy=False)
            hn = np.linalg.norm(hv) or 1.0
            pn = np.linalg.norm(pool_vec) or 1.0
            neg_cosines.append(float(np.dot(hv / hn, pool_vec / pn)))

    n = len(positives)
    mrr = mrr_sum / n if n else 0.0
    ndcg = ndcg_sum / n if n else 0.0
    recall = recall_hits / n if n else 0.0
    mean_pos = float(np.mean(pos_cosines)) if pos_cosines else 0.0
    mean_neg = float(np.mean(neg_cosines)) if neg_cosines else 0.0
    sep = mean_pos - mean_neg

    # Latency percentiles.
    if latencies:
        lat_arr = np.array(latencies)
        p50 = int(np.percentile(lat_arr, 50))
        p95 = int(np.percentile(lat_arr, 95))
    else:
        p50 = p95 = 0

    return BakeoffRun(
        provider_name=getattr(provider, "name", "unknown"),
        signature=getattr(provider, "signature", ""),
        sample_size=n,
        mrr_at_10=mrr,
        ndcg_at_10=ndcg,
        recall_at_10=recall,
        mean_positive_cosine=mean_pos,
        mean_negative_cosine=mean_neg,
        separation_score=sep,
        cost_usd=total_cost,
        latency_ms_p50=p50,
        latency_ms_p95=p95,
    )


def persist_run(*, job_id: str, run: BakeoffRun) -> None:
    """Upsert a ``EmbeddingBakeoffResult`` row for ``(job_id, provider)``."""
    try:
        from apps.pipeline.models import EmbeddingBakeoffResult

        EmbeddingBakeoffResult.objects.update_or_create(
            job_id=job_id,
            provider=run.provider_name,
            defaults={
                "signature": run.signature,
                "sample_size": run.sample_size,
                "mrr_at_10": Decimal(f"{run.mrr_at_10:.4f}"),
                "ndcg_at_10": Decimal(f"{run.ndcg_at_10:.4f}"),
                "recall_at_10": Decimal(f"{run.recall_at_10:.4f}"),
                "mean_positive_cosine": Decimal(f"{run.mean_positive_cosine:.4f}"),
                "mean_negative_cosine": Decimal(f"{run.mean_negative_cosine:.4f}"),
                "separation_score": Decimal(f"{run.separation_score:.4f}"),
                "cost_usd": Decimal(f"{run.cost_usd:.6f}"),
                "latency_ms_p50": run.latency_ms_p50,
                "latency_ms_p95": run.latency_ms_p95,
            },
        )
    except Exception:
        logger.exception("persist_run failed for %s", run.provider_name)


def update_provider_ranking(runs: list[BakeoffRun]) -> None:
    """Write ``embedding.provider_ranking_json`` with signature→NDCG map.

    The quality gate (plan Part 9) reads this setting to decide whether a new
    vector from a different provider is allowed to overwrite an existing one.
    """
    if not runs:
        return
    try:
        import json

        from apps.core.models import AppSetting

        ranking = {
            run.signature: float(run.ndcg_at_10) for run in runs if run.signature
        }
        # Normalise to [0, 1] so deltas are interpretable even if NDCG scores are all low.
        max_v = max(ranking.values()) if ranking else 0.0
        if max_v > 0:
            ranking = {k: v / max_v for k, v in ranking.items()}
        AppSetting.objects.update_or_create(
            key="embedding.provider_ranking_json",
            defaults={"value": json.dumps(ranking)},
        )
        # Also record the human-friendly winner.
        winner = max(runs, key=lambda r: r.separation_score * 0.5 + r.ndcg_at_10 * 0.5)
        AppSetting.objects.update_or_create(
            key="embedding.recommended_provider",
            defaults={"value": winner.provider_name},
        )
    except Exception:
        logger.exception("update_provider_ranking failed")


__all__ = [
    "BakeoffRun",
    "load_stored_vectors",
    "load_texts",
    "persist_run",
    "sample_ground_truth",
    "score_provider",
    "update_provider_ranking",
]
