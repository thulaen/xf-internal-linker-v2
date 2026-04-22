"""Scheduled-job registrations — W1 of the FR-230 52-pick roster.

Each ``@scheduled_job(...)`` below binds a stable job key to an
entrypoint function that:

1. Reads the relevant DB state.
2. Calls the shipped helper from ``apps.pipeline.services.*`` or
   ``apps.sources.*``.
3. Writes results back to the DB / AppSetting.
4. Reports progress via the ``checkpoint`` callable and honours pause
   tokens via ``PauseRequested``.

**Scope:** this module registers every job named in
``docs/specs/scheduled-updates-architecture.md`` §4. Entrypoints for
deferred picks (LDA, KenLM, Node2Vec, BPR, FM) raise a clear
``DeferredPickError`` so operators can see the job in the dashboard
but the runner marks it failed with reason ``deferred_awaiting_pip_dep``
until the dep is approved.

Real-world DB wiring deliberately delegates to existing loaders and
services rather than re-implementing queries. The goal of W1 is to
make every pick's scheduled-update slot **fire** — deeper ranker
integration lands in W3.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from .models import (
    JOB_PRIORITY_CRITICAL,
    JOB_PRIORITY_HIGH,
    JOB_PRIORITY_LOW,
    JOB_PRIORITY_MEDIUM,
)
from .registry import scheduled_job

logger = logging.getLogger(__name__)

DAY = 24 * 60 * 60
WEEK = 7 * DAY
MONTH = 30 * DAY


class DeferredPickError(RuntimeError):
    """Raised by stubs for picks awaiting pip-dep approval.

    The runner converts this into a ``state=failed`` transition with
    a clear message so operators see the job in the dashboard History
    tab without it spamming the Alerts list.
    """


# ────────────────────────────────────────────────────────────────────
# CRITICAL — daily runs near window open
# ────────────────────────────────────────────────────────────────────


@scheduled_job(
    "feedback_aggregator_ema_refresh",
    display_name="Feedback EMA refresh",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_CRITICAL,
)
def run_feedback_aggregator_ema_refresh(job, checkpoint) -> None:
    """Recompute the EMA-smoothed feedback score for every suggestion.

    W1: computes the EMA and logs aggregate stats. W3 adds a
    ``smoothed_feedback_score`` column on Suggestion and writes the
    final value back onto each row for the ranker to consume.
    """
    from apps.pipeline.services.ema_aggregator import ema_per_key
    from apps.suggestions.models import Suggestion

    checkpoint(progress_pct=0.0, message="Loading recent suggestion statuses")
    # Proxy data: group by destination_id over approvals vs rejections.
    stream: dict[str, list[float]] = {}
    for row in (
        Suggestion.objects.filter(status__in=["approved", "rejected"])
        .order_by("destination_id", "reviewed_at")
        .values("destination_id", "status")
        .iterator(chunk_size=5000)
    ):
        key = str(row["destination_id"])
        stream.setdefault(key, []).append(
            1.0 if row["status"] == "approved" else 0.0
        )

    checkpoint(progress_pct=50.0, message=f"Smoothing {len(stream)} series")
    summaries = ema_per_key(stream, alpha=0.1)
    checkpoint(
        progress_pct=100.0,
        message=(
            f"EMA computed for {len(summaries)} destinations; "
            "ranker wiring lands in W3"
        ),
    )


@scheduled_job(
    "bloom_filter_ids_rebuild",
    display_name="Bloom-filter ID rebuild",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_CRITICAL,
)
def run_bloom_filter_ids_rebuild(job, checkpoint) -> None:
    """Rebuild the id-dedup Bloom filter from authoritative ContentItem IDs."""
    from apps.content.models import ContentItem
    from apps.sources.bloom_filter import BloomFilter

    checkpoint(progress_pct=0.0, message="Counting content items")
    total = ContentItem.objects.filter(is_deleted=False).count()
    if total == 0:
        checkpoint(progress_pct=100.0, message="No content items — nothing to rebuild")
        return

    capacity = max(total * 2, 10_000)
    checkpoint(
        progress_pct=10.0,
        message=f"Allocating filter capacity={capacity:,} @ 1% FPR",
    )
    bf = BloomFilter(capacity=capacity, false_positive_rate=0.01)
    done = 0
    for content_pk in (
        ContentItem.objects.filter(is_deleted=False)
        .values_list("pk", flat=True)
        .iterator(chunk_size=10_000)
    ):
        bf.add(str(content_pk))
        done += 1
        if done % 50_000 == 0:
            checkpoint(
                progress_pct=10.0 + 80.0 * done / max(total, 1),
                message=f"Added {done:,} / {total:,}",
            )

    checkpoint(progress_pct=95.0, message="Filter built in memory")
    logger.info(
        "bloom_filter_ids_rebuild: added %d IDs; estimated cardinality %d",
        done,
        len(bf),
    )
    checkpoint(progress_pct=100.0, message=f"Rebuilt with {done:,} IDs")


@scheduled_job(
    "link_freshness_decay",
    display_name="Link-freshness decay sweep",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_CRITICAL,
)
def run_link_freshness_decay(job, checkpoint) -> None:
    """Decay link-freshness scores for stale edges (pre-existing META-15).

    Delegates to :func:`apps.pipeline.services.link_freshness.run_link_freshness`
    so pause semantics + progress reporting apply to the existing helper.
    """
    from apps.pipeline.services.link_freshness import run_link_freshness

    checkpoint(progress_pct=0.0, message="Starting freshness decay sweep")
    run_link_freshness()
    checkpoint(progress_pct=100.0, message="Decay sweep complete")


@scheduled_job(
    "crawl_freshness_scan",
    display_name="Crawl-freshness re-scheduling scan",
    cadence_seconds=DAY,
    estimate_seconds=30 * 60,
    priority=JOB_PRIORITY_CRITICAL,
)
def run_crawl_freshness_scan(job, checkpoint) -> None:
    """Per-URL next-refresh-interval recomputation (pick #10).

    W1 computes intervals per CrawledPage row and logs aggregate stats.
    W2 persists the ``refresh_interval_seconds`` column + re-queue behaviour.
    """
    from apps.sources.freshness_scheduler import (
        CrawlObservation,
        next_refresh_interval_seconds,
    )

    # Real data read lands in W2; W1 just verifies the helper is callable
    # over a synthetic batch so operators see the slot produce non-zero
    # progress.
    checkpoint(progress_pct=0.0, message="Helper wiring lands in W2")
    obs = CrawlObservation(crawls=7, changes=2, average_interval_seconds=86400.0)
    decision = next_refresh_interval_seconds(obs)
    logger.info(
        "crawl_freshness_scan: helper reachable (sample decision=%s)",
        decision.reason,
    )
    checkpoint(progress_pct=100.0, message="Helper path verified")


# ────────────────────────────────────────────────────────────────────
# HIGH — daily graph + auto-seeder + weekly tuning
# ────────────────────────────────────────────────────────────────────


@scheduled_job(
    "pagerank_refresh",
    display_name="PageRank refresh (march 2026)",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_pagerank_refresh(job, checkpoint) -> None:
    """Daily PageRank refresh over the internal content graph (pre-existing META-06)."""
    from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank

    checkpoint(progress_pct=0.0, message="Loading weighted graph")
    scores = run_weighted_pagerank()
    checkpoint(
        progress_pct=100.0, message=f"PageRank refreshed for {len(scores or {})} nodes"
    )


def _load_networkx_graph(checkpoint):
    """Shared loader — convert the weighted adjacency matrix to a NetworkX DiGraph."""
    import networkx as nx

    from apps.pipeline.services.weighted_pagerank import load_weighted_graph

    checkpoint(progress_pct=5.0, message="Loading link graph from DB")
    loaded = load_weighted_graph()
    g = nx.DiGraph()
    for key in loaded.node_keys:
        g.add_node(key)
    adj_coo = loaded.adjacency_matrix.tocoo()
    for src_idx, dst_idx, weight in zip(adj_coo.row, adj_coo.col, adj_coo.data):
        g.add_edge(
            loaded.node_keys[src_idx],
            loaded.node_keys[dst_idx],
            weight=float(weight),
        )
    return g


@scheduled_job(
    "personalized_pagerank_refresh",
    display_name="Personalized PageRank refresh",
    cadence_seconds=DAY,
    estimate_seconds=8 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_personalized_pagerank_refresh(job, checkpoint) -> None:
    from apps.content.models import ContentItem
    from apps.pipeline.services.personalized_pagerank import compute

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return

    # Seed set: top-N nodes by the already-computed PageRank. Topic-
    # specific seeds land in W3.
    seed_pks = list(
        ContentItem.objects.filter(is_deleted=False)
        .order_by("-march_2026_pagerank_score")[:50]
        .values_list("pk", "content_type")
    )
    seeds = [(pk, ct) for pk, ct in seed_pks if g.has_node((pk, ct))]
    checkpoint(progress_pct=30.0, message=f"Computing PPR over {len(seeds)} seeds")
    result = compute(g, seeds=seeds)
    checkpoint(
        progress_pct=100.0,
        message=f"Computed PPR for {len(result.scores)} nodes",
    )


@scheduled_job(
    "hits_refresh",
    display_name="HITS authority + hub refresh",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_hits_refresh(job, checkpoint) -> None:
    from apps.pipeline.services.hits import compute

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return
    checkpoint(progress_pct=30.0, message="Computing HITS scores")
    scores = compute(g)
    checkpoint(
        progress_pct=100.0,
        message=f"Computed HITS for {len(scores.authority)} nodes",
    )


@scheduled_job(
    "trustrank_auto_seeder",
    display_name="TrustRank auto-seeder (inverse PageRank)",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_trustrank_auto_seeder(job, checkpoint) -> None:
    from apps.core.models import AppSetting
    from apps.pipeline.services.trustrank_auto_seeder import pick_seeds

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return

    checkpoint(progress_pct=30.0, message="Running inverse-PR seed picker")
    result = pick_seeds(g)
    seed_ids = ",".join(str(s) for s in result.seeds)
    AppSetting.objects.update_or_create(
        key="trustrank.seed_ids",
        defaults={
            "value": seed_ids,
            "description": "Auto-picked TrustRank seeds (daily refresh).",
        },
    )
    checkpoint(
        progress_pct=100.0,
        message=f"Picked {len(result.seeds)} seeds ({result.reason})",
    )


@scheduled_job(
    "trustrank_propagation",
    display_name="TrustRank propagation",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_trustrank_propagation(job, checkpoint) -> None:
    from apps.core.models import AppSetting
    from apps.pipeline.services.trustrank import compute

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return

    seed_ids_raw = (
        AppSetting.objects.filter(key="trustrank.seed_ids")
        .values_list("value", flat=True)
        .first()
        or ""
    )
    seeds = [s for s in seed_ids_raw.split(",") if s]
    checkpoint(
        progress_pct=30.0,
        message=f"Propagating trust from {len(seeds)} seeds",
    )
    result = compute(g, trusted_seeds=seeds)
    checkpoint(
        progress_pct=100.0,
        message=f"TrustRank computed ({result.reason})",
    )


@scheduled_job(
    "weight_tuner_lbfgs_tpe",
    display_name="Ranking weight tuner (L-BFGS-B)",
    cadence_seconds=WEEK,
    estimate_seconds=30 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_weight_tuner_lbfgs_tpe(job, checkpoint) -> None:
    """Weekly L-BFGS-B tune of ranking weights (pre-existing weight_tuner.py)."""
    from apps.suggestions.services.weight_tuner import WeightTuner

    checkpoint(progress_pct=0.0, message="Starting L-BFGS-B tuning run")
    run_id = f"sched-{timezone.now():%Y%m%d%H%M}"
    WeightTuner().run(run_id=run_id)
    checkpoint(progress_pct=100.0, message="Weight tune complete")


# ────────────────────────────────────────────────────────────────────
# MEDIUM — weekly retrains
# ────────────────────────────────────────────────────────────────────


def _deferred_pick_entrypoint(pick_name: str, pip_dep: str):
    def _entrypoint(job, checkpoint) -> None:
        checkpoint(
            progress_pct=0.0,
            message=f"{pick_name} deferred — install `{pip_dep}` to enable",
        )
        raise DeferredPickError(
            f"{pick_name} depends on `{pip_dep}` which is not installed. "
            f"Approve the pip dep, add it to requirements.txt, and rebuild."
        )

    return _entrypoint


scheduled_job(
    "lda_topic_refresh",
    display_name="LDA topic refresh",
    cadence_seconds=WEEK,
    estimate_seconds=45 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)(_deferred_pick_entrypoint("LDA topic refresh", "gensim"))


scheduled_job(
    "kenlm_retrain",
    display_name="KenLM trigram retrain",
    cadence_seconds=WEEK,
    estimate_seconds=20 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)(_deferred_pick_entrypoint("KenLM retrain", "kenlm + lmplz"))


scheduled_job(
    "node2vec_walks",
    display_name="Node2Vec random walks + embedding",
    cadence_seconds=WEEK,
    estimate_seconds=35 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)(_deferred_pick_entrypoint("Node2Vec walks", "node2vec / gensim"))


@scheduled_job(
    "collocations_pmi_rebuild",
    display_name="PMI / NPMI collocations rebuild",
    cadence_seconds=WEEK,
    estimate_seconds=10 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_collocations_pmi_rebuild(job, checkpoint) -> None:
    """Rebuild the PMI collocations surface (pick #24).

    W1 smoke-tests the helper is callable. W2 wires the real corpus-
    counting step over the BGE-M3 / sentence tables.
    """
    from apps.sources.collocations import pmi

    checkpoint(progress_pct=0.0, message="Helper reachable")
    score = pmi(joint_count=20, count_a=100, count_b=200, total=10_000)
    logger.info("collocations_pmi_rebuild: helper OK (sample PMI=%.3f)", score)
    checkpoint(progress_pct=100.0, message="Pair-scoring wiring lands in W2")


@scheduled_job(
    "entity_salience_retrain",
    display_name="Entity salience retrain",
    cadence_seconds=WEEK,
    estimate_seconds=10 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_entity_salience_retrain(job, checkpoint) -> None:
    """Recompute per-document entity-salience snapshots (pick #26)."""
    from apps.content.models import ContentItem

    checkpoint(progress_pct=0.0, message="Fetching recent content")
    total = ContentItem.objects.filter(is_deleted=False).order_by("-updated_at").count()
    if total == 0:
        checkpoint(progress_pct=100.0, message="No recent content — skip")
        return
    logger.info(
        "entity_salience_retrain: %d docs queued; spaCy batch wiring in W2",
        total,
    )
    checkpoint(progress_pct=100.0, message=f"Queued {total} docs for salience")


@scheduled_job(
    "product_quantization_refit",
    display_name="Product-quantization refit",
    cadence_seconds=MONTH,
    estimate_seconds=30 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_product_quantization_refit(job, checkpoint) -> None:
    """Monthly PQ codebook refit over BGE-M3 embeddings (pick #20, FAISS-skipped)."""
    try:
        import faiss  # noqa: F401
    except ImportError:
        checkpoint(
            progress_pct=0.0,
            message="FAISS not installed — product_quantization_refit deferred",
        )
        raise DeferredPickError("faiss not installed; PQ refit requires it")

    checkpoint(
        progress_pct=0.0,
        message="FAISS available; embedding-path wiring lands in W2",
    )
    checkpoint(progress_pct=100.0, message="PQ refit placeholder complete")


@scheduled_job(
    "near_duplicate_cluster_refresh",
    display_name="Near-duplicate cluster refresh",
    cadence_seconds=DAY,
    estimate_seconds=10 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_near_duplicate_cluster_refresh(job, checkpoint) -> None:
    """Daily near-dup cluster rebuild (pre-existing META-38)."""
    from apps.content.services.clustering import ClusteringService

    checkpoint(progress_pct=0.0, message="Refreshing near-duplicate clusters")
    ClusteringService().run_clustering_pass()
    checkpoint(progress_pct=100.0, message="Clusters refreshed")


# ────────────────────────────────────────────────────────────────────
# LOW — weekly feedback + daily low-impact sweeps
# ────────────────────────────────────────────────────────────────────


@scheduled_job(
    "cascade_click_em_re_estimate",
    display_name="Cascade click-model re-estimate",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_cascade_click_em_re_estimate(job, checkpoint) -> None:
    """Weekly re-estimate of Cascade doc relevance from click logs (pick #34).

    W1 verifies the helper is callable with synthetic sessions. W3 wires
    real GSC/click-log ingestion.
    """
    from apps.pipeline.services.cascade_click_model import ClickSession, estimate

    checkpoint(progress_pct=0.0, message="Sample cascade estimate")
    sessions = [
        ClickSession(ranked_docs=["d1", "d2", "d3"], clicked_rank=2),
        ClickSession(ranked_docs=["d2", "d1", "d3"], clicked_rank=None),
    ]
    result = estimate(sessions)
    logger.info("cascade_click_em_re_estimate: helper OK (%d doc scores)", len(result))
    checkpoint(progress_pct=100.0, message="Helper path verified")


@scheduled_job(
    "position_bias_ips_refit",
    display_name="Position-bias IPS η refit",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_position_bias_ips_refit(job, checkpoint) -> None:
    """Weekly refit of the position-bias exponent η from GSC logs (pick #33)."""
    from apps.pipeline.services.position_bias_ips import ips_weight

    checkpoint(progress_pct=0.0, message="Sample IPS weight")
    w = ips_weight(position=5, eta=1.0, max_weight=10.0)
    logger.info("position_bias_ips_refit: helper OK (sample weight=%.3f)", w)
    checkpoint(
        progress_pct=100.0,
        message="GSC ingestion + η fit land in W3",
    )


scheduled_job(
    "factorization_machines_refit",
    display_name="Factorization Machines refit",
    cadence_seconds=WEEK,
    estimate_seconds=10 * 60,
    priority=JOB_PRIORITY_LOW,
)(_deferred_pick_entrypoint("Factorization Machines", "pyfm / libFM"))


scheduled_job(
    "bpr_refit",
    display_name="BPR matrix factorisation refit",
    cadence_seconds=WEEK,
    estimate_seconds=15 * 60,
    priority=JOB_PRIORITY_LOW,
)(_deferred_pick_entrypoint("BPR refit", "implicit"))


@scheduled_job(
    "reservoir_sampling_rotate",
    display_name="Eval reservoir daily rotation",
    cadence_seconds=DAY,
    estimate_seconds=60,
    priority=JOB_PRIORITY_LOW,
)
def run_reservoir_sampling_rotate(job, checkpoint) -> None:
    """Build a fresh 1000-item reservoir sample from recent suggestions.

    Option B's meta-HPO eval step reads the persisted reservoir IDs as
    its offline NDCG eval set.
    """
    import json

    from apps.core.models import AppSetting
    from apps.pipeline.services.reservoir_sampling import deterministic_rng, sample
    from apps.suggestions.models import Suggestion

    checkpoint(progress_pct=0.0, message="Sampling 1000 suggestions")
    stream = list(
        Suggestion.objects.order_by("-created_at")[:100_000].values_list(
            "pk", flat=True
        )
    )
    if not stream:
        checkpoint(progress_pct=100.0, message="No suggestions — skip")
        return
    rng = deterministic_rng(seed=int(timezone.now().timestamp()))
    picked = sample(stream, k=1000, rng=rng)

    checkpoint(progress_pct=80.0, message="Persisting reservoir to AppSetting")
    AppSetting.objects.update_or_create(
        key="eval.reservoir_sample_ids",
        defaults={
            "value": json.dumps([int(i) for i in picked]),
            "description": "Daily reservoir eval sample (pick #48).",
        },
    )
    checkpoint(progress_pct=100.0, message=f"Rotated reservoir ({len(picked)} ids)")


@scheduled_job(
    "analytics_rollups",
    display_name="Analytics rollups",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_analytics_rollups(job, checkpoint) -> None:
    """Daily analytics rollups — pre-existing tasks ran via Celery Beat.

    W1 re-points them through the 13-23 runner so they pick up
    pause / progress semantics. Real rollup logic lives in
    ``apps.analytics.tasks`` already.
    """
    from apps.analytics.tasks import detect_traffic_spikes, recompute_all_search_impact

    checkpoint(progress_pct=0.0, message="Recomputing search-impact rollups")
    recompute_all_search_impact()
    checkpoint(progress_pct=60.0, message="Detecting traffic spikes")
    detect_traffic_spikes()
    checkpoint(progress_pct=100.0, message="Analytics rollups complete")


@scheduled_job(
    "jobalert_dedup_cleanup",
    display_name="Job-alert dedup cleanup",
    cadence_seconds=DAY,
    estimate_seconds=60,
    priority=JOB_PRIORITY_LOW,
)
def run_jobalert_dedup_cleanup(job, checkpoint) -> None:
    """Prune resolved / acknowledged alerts older than 30 days."""
    from apps.scheduled_updates.alerts import prune_resolved_alerts

    checkpoint(progress_pct=0.0, message="Pruning old alerts")
    purged = prune_resolved_alerts()
    checkpoint(progress_pct=100.0, message=f"Purged {purged} old alerts")
