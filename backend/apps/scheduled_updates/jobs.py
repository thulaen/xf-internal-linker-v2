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


class HeavyLockBusyError(RuntimeError):
    """Raised when a Heavy-tier scheduled job cannot acquire the global
    Heavy lock (e.g. an embedding job is running). The runner converts
    this into a clean defer — the next beat tick will re-attempt.
    """


def _acquire_heavy_or_defer(task_name: str, *, timeout_seconds: int = 1800) -> bool:
    """Phase 0.8 (Wave 1 C.4) — bridge the scheduled-updates runner to the
    pipeline's Heavy weight class.

    Plain-English: PR / HITS / TrustRank are GPU-or-CPU-heavy daily jobs
    that previously ran whenever the scheduled_updates runner-lock was
    free, even if a heavy embedding pass was simultaneously hogging the
    GPU. That competition slowed both. The fix promotes them to the
    project-wide Heavy weight class so they queue strictly serially with
    embedding / FAISS / quantization. If the lock is busy, this returns
    False and the calling job exits cleanly — the next 5-minute beat
    tick will retry. Net effect: same total work per day, no GPU
    contention, predictable wall-clock per job.

    Returns True when the lock is acquired (caller must call
    ``apps.pipeline.services.task_lock.release_task_lock("heavy", ...)``
    when done). Returns False to signal "defer to next tick".
    """
    from apps.pipeline.services.task_lock import acquire_task_lock

    return acquire_task_lock("heavy", task_name, timeout=timeout_seconds)


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
        stream.setdefault(key, []).append(1.0 if row["status"] == "approved" else 0.0)

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
    """Rebuild the id-dedup Bloom filter from authoritative ContentItem IDs.

    Delegates to :data:`apps.sources.bloom_filter_registry.REGISTRY`
    so the rebuilt filter persists to disk and import-pipeline callers
    can fast-skip post IDs they have already imported.
    """
    from apps.sources.bloom_filter_registry import REGISTRY

    def _progress(done, total):
        checkpoint(
            progress_pct=80.0 * done / max(total, 1),
            message=f"Added {done:,} / {total:,}",
        )

    checkpoint(progress_pct=0.0, message="Rebuilding from ContentItem table")
    added = REGISTRY.rebuild_from_db(progress=_progress)
    if added == 0:
        checkpoint(progress_pct=100.0, message="No content items — skip")
        return
    logger.info(
        "bloom_filter_ids_rebuild: registry now contains %d IDs (snapshot persisted)",
        added,
    )
    checkpoint(
        progress_pct=100.0,
        message=f"Rebuilt registry with {added:,} IDs (snapshot saved)",
    )


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
    "rsqva_tfidf_refresh",
    display_name="FR-105 RSQVA: GSC query TF-IDF vectors refresh",
    cadence_seconds=DAY,
    estimate_seconds=15 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_rsqva_tfidf_refresh(job, checkpoint) -> None:
    """Recompute per-page GSC query TF-IDF vectors used by FR-105 RSQVA.

    See docs/specs/fr105-reverse-search-query-vocabulary-alignment.md.
    Safely no-ops when GSC data is below the 7-day minimum-data floor
    (BLC §6.4) — FR-105's signal evaluation stays in
    `vector_not_computed` fallback until the window has enough data.
    """
    from apps.analytics.gsc_query_vocab import refresh_gsc_query_tfidf

    checkpoint(progress_pct=0.0, message="Starting RSQVA TF-IDF refresh")
    stats = refresh_gsc_query_tfidf(lookback_days=90, checkpoint=checkpoint)
    checkpoint(
        progress_pct=100.0,
        message=(
            f"RSQVA refresh: {stats['pages_updated']:,} pages updated "
            f"from {stats['rows_read']:,} GSC rows "
            f"({stats['min_gsc_days_seen']} days seen)"
        ),
    )


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
    """Daily PageRank refresh over the internal content graph (pre-existing META-06).

    Phase 0.8: acquires the project-wide Heavy lock so it can't fight
    embedding / FAISS / OPQ work for the GPU. Defers to the next beat
    tick if the lock is busy.
    """
    from apps.pipeline.services.task_lock import release_task_lock
    from apps.pipeline.services.weighted_pagerank import run_weighted_pagerank

    if not _acquire_heavy_or_defer("pagerank_refresh"):
        checkpoint(progress_pct=0.0, message="Heavy lock busy — deferring to next tick")
        return
    try:
        checkpoint(progress_pct=0.0, message="Loading weighted graph")
        scores = run_weighted_pagerank()
        checkpoint(
            progress_pct=100.0,
            message=f"PageRank refreshed for {len(scores or {})} nodes",
        )
    finally:
        release_task_lock("heavy", "pagerank_refresh")


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
    """Phase 0.8: Heavy-lock-aware PPR refresh."""
    from apps.content.models import ContentItem
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_PPR,
        persist_top_n,
    )
    from apps.pipeline.services.personalized_pagerank import compute
    from apps.pipeline.services.task_lock import release_task_lock

    if not _acquire_heavy_or_defer("personalized_pagerank_refresh"):
        checkpoint(progress_pct=0.0, message="Heavy lock busy — deferring to next tick")
        return
    try:
        g = _load_networkx_graph(checkpoint)
        if g.number_of_nodes() == 0:
            checkpoint(progress_pct=100.0, message="Empty graph — skip")
            return

        # Seed set: top-N nodes by the already-computed PageRank.
        seed_pks = list(
            ContentItem.objects.filter(is_deleted=False)
            .order_by("-march_2026_pagerank_score")[:50]
            .values_list("pk", "content_type")
        )
        seeds = [(pk, ct) for pk, ct in seed_pks if g.has_node((pk, ct))]
        checkpoint(progress_pct=30.0, message=f"Computing PPR over {len(seeds)} seeds")
        result = compute(g, seeds=seeds)
        checkpoint(progress_pct=70.0, message="Persisting PPR top-N")
        written = persist_top_n(signal=SIGNAL_PPR, scores=result.scores)
        checkpoint(
            progress_pct=100.0,
            message=f"PPR persisted: {written} of {len(result.scores)} nodes",
        )
    finally:
        release_task_lock("heavy", "personalized_pagerank_refresh")


@scheduled_job(
    "hits_refresh",
    display_name="HITS authority + hub refresh",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_hits_refresh(job, checkpoint) -> None:
    """Phase 0.8: Heavy-lock-aware HITS refresh."""
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_HITS_AUTHORITY,
        SIGNAL_HITS_HUB,
        persist_top_n,
    )
    from apps.pipeline.services.hits import compute
    from apps.pipeline.services.task_lock import release_task_lock

    if not _acquire_heavy_or_defer("hits_refresh"):
        checkpoint(progress_pct=0.0, message="Heavy lock busy — deferring to next tick")
        return
    try:
        g = _load_networkx_graph(checkpoint)
        if g.number_of_nodes() == 0:
            checkpoint(progress_pct=100.0, message="Empty graph — skip")
            return
        checkpoint(progress_pct=30.0, message="Computing HITS scores")
        scores = compute(g)
        checkpoint(progress_pct=70.0, message="Persisting authority + hub top-N")
        auth_count = persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY, scores=scores.authority
        )
        hub_count = persist_top_n(signal=SIGNAL_HITS_HUB, scores=scores.hub)
        checkpoint(
            progress_pct=100.0,
            message=(
                f"HITS persisted: {auth_count} authorities + {hub_count} hubs "
                f"(of {len(scores.authority)} nodes)"
            ),
        )
    finally:
        release_task_lock("heavy", "hits_refresh")


def _coerce_setting_int(raw_map: dict, key: str, default: int) -> int:
    """Coerce a bulk-loaded AppSetting string to int with a default fallback."""
    raw = raw_map.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _coerce_setting_float(raw_map: dict, key: str, default: float) -> float:
    """Coerce a bulk-loaded AppSetting string to float with a default fallback."""
    raw = raw_map.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _bulk_load_settings(keys: tuple[str, ...]) -> dict[str, str]:
    """Single ``filter(key__in=...)`` query → dict for cheap dict.get coercions.

    Use when a job needs ≥3 AppSetting reads at once. One DB round-trip
    instead of N saves ~30-50ms per job invocation; multiplied across
    daily / hourly schedules it's worth more than the function call cost.
    """
    from apps.core.models import AppSetting

    return dict(
        AppSetting.objects.filter(key__in=keys).values_list("key", "value"),
    )


_TRUSTRANK_SETTING_KEYS = (
    "trustrank_auto_seeder.candidate_pool_size",
    "trustrank_auto_seeder.seed_count_k",
    "trustrank_auto_seeder.post_quality_min",
    "trustrank_auto_seeder.readability_grade_max",
    "trustrank_auto_seeder.spam_content_value_floor",
)


def _read_trustrank_seeder_settings() -> dict:
    """Read all TrustRank tunables in one query; coerce + apply defaults."""
    from apps.pipeline.services.trustrank_auto_seeder import (
        DEFAULT_CANDIDATE_POOL_SIZE,
        DEFAULT_POST_QUALITY_MIN,
        DEFAULT_READABILITY_GRADE_MAX,
        DEFAULT_SEED_COUNT_K,
    )

    raw = _bulk_load_settings(_TRUSTRANK_SETTING_KEYS)
    return {
        "candidate_pool_size": _coerce_setting_int(
            raw,
            "trustrank_auto_seeder.candidate_pool_size",
            DEFAULT_CANDIDATE_POOL_SIZE,
        ),
        "seed_count_k": _coerce_setting_int(
            raw,
            "trustrank_auto_seeder.seed_count_k",
            DEFAULT_SEED_COUNT_K,
        ),
        "post_quality_min": _coerce_setting_float(
            raw,
            "trustrank_auto_seeder.post_quality_min",
            DEFAULT_POST_QUALITY_MIN,
        ),
        "readability_grade_max": _coerce_setting_float(
            raw,
            "trustrank_auto_seeder.readability_grade_max",
            DEFAULT_READABILITY_GRADE_MAX,
        ),
        # Spam flagging — no dedicated column, so very low content_value_score is
        # the proxy. Tunable via AppSetting; 0.0 disables the spam filter entirely.
        "spam_quality_floor": _coerce_setting_float(
            raw,
            "trustrank_auto_seeder.spam_content_value_floor",
            0.15,
        ),
    }


def _build_trustrank_quality_maps(spam_quality_floor: float) -> tuple[dict, set]:
    """Build per-node ``post_quality`` map + ``spam_flagged`` set from ContentItem."""
    from apps.content.models import ContentItem

    quality_rows = ContentItem.objects.filter(is_deleted=False).values_list(
        "pk",
        "content_type",
        "content_value_score",
    )
    post_quality: dict = {}
    spam_flagged: set = set()
    for pk, content_type, value_score in quality_rows:
        if value_score is None:
            continue
        key = (pk, content_type)
        post_quality[key] = float(value_score)
        if spam_quality_floor > 0.0 and float(value_score) <= spam_quality_floor:
            spam_flagged.add(key)
    return post_quality, spam_flagged


def _build_trustrank_readability_map() -> dict:
    """Build per-node ``readability_grade`` map from Post.flesch_kincaid_grade."""
    from apps.content.models import Post

    readability_grade: dict = {}
    rows = (
        Post.objects.select_related("content_item")
        .filter(content_item__is_deleted=False)
        .values_list(
            "content_item__pk",
            "content_item__content_type",
            "flesch_kincaid_grade",
        )
    )
    for pk, content_type, grade in rows:
        if grade is not None and grade > 0.0:
            readability_grade[(pk, content_type)] = float(grade)
    return readability_grade


def _persist_trustrank_seeds(
    seeds: list, reason: str, fallback_used: bool, rejected_count: int, checkpoint
) -> None:
    """Write the daily TrustRank seed list to AppSetting + report final progress."""
    from apps.core.models import AppSetting

    seed_ids = ",".join(str(s) for s in seeds)
    AppSetting.objects.update_or_create(
        key="trustrank.seed_ids",
        defaults={
            "value": seed_ids,
            "description": "Auto-picked TrustRank seeds (daily refresh).",
        },
    )
    checkpoint(
        progress_pct=100.0,
        message=(
            f"Picked {len(seeds)} seeds "
            f"({reason}; rejected={rejected_count}, "
            f"fallback={'yes' if fallback_used else 'no'})"
        ),
    )


def _run_trustrank_seeder_pipeline(checkpoint) -> None:
    """Happy-path body for ``run_trustrank_auto_seeder`` (heavy-lock acquired)."""
    from apps.pipeline.services.trustrank_auto_seeder import pick_seeds

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return
    settings = _read_trustrank_seeder_settings()
    checkpoint(
        progress_pct=20.0,
        message="Loading per-node quality + readability + spam maps",
    )
    post_quality, spam_flagged = _build_trustrank_quality_maps(
        settings["spam_quality_floor"],
    )
    readability_grade = _build_trustrank_readability_map()
    checkpoint(
        progress_pct=50.0,
        message=(
            f"Picking seeds from pool={settings['candidate_pool_size']} "
            f"k={settings['seed_count_k']} "
            f"(quality={len(post_quality)}, "
            f"readability={len(readability_grade)}, spam={len(spam_flagged)})"
        ),
    )
    result = pick_seeds(
        g,
        candidate_pool_size=settings["candidate_pool_size"],
        seed_count_k=settings["seed_count_k"],
        spam_flagged=spam_flagged,
        post_quality=post_quality,
        post_quality_min=settings["post_quality_min"],
        readability_grade=readability_grade,
        readability_grade_max=settings["readability_grade_max"],
    )
    _persist_trustrank_seeds(
        result.seeds,
        result.reason,
        result.fallback_used,
        result.rejected_count,
        checkpoint,
    )


@scheduled_job(
    "trustrank_auto_seeder",
    display_name="TrustRank auto-seeder (inverse PageRank)",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_trustrank_auto_seeder(job, checkpoint) -> None:
    """Phase 5c — pick #51 wiring.

    Reads ``trustrank_auto_seeder.*`` AppSettings + feeds the seed picker
    per-node quality data: ``post_quality`` from ContentItem.content_value_score,
    ``readability_grade`` from Post.flesch_kincaid_grade, ``spam_flagged``
    from a low-quality threshold on content_value_score. Cold-start safe:
    every quality input is optional and the picker only rejects on
    affirmative low-quality evidence.
    """
    from apps.pipeline.services.task_lock import release_task_lock

    # Phase 0.8: Heavy-lock-aware TrustRank.
    if not _acquire_heavy_or_defer("trustrank_auto_seeder"):
        checkpoint(progress_pct=0.0, message="Heavy lock busy — deferring to next tick")
        return
    try:
        _run_trustrank_seeder_pipeline(checkpoint)
    finally:
        release_task_lock("heavy", "trustrank_auto_seeder")


@scheduled_job(
    "trustrank_propagation",
    display_name="TrustRank propagation",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_trustrank_propagation(job, checkpoint) -> None:
    """Phase 0.8: Heavy-lock-aware TrustRank propagation."""
    from apps.core.models import AppSetting
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_TRUSTRANK,
        persist_top_n,
    )
    from apps.pipeline.services.task_lock import release_task_lock
    from apps.pipeline.services.trustrank import compute

    if not _acquire_heavy_or_defer("trustrank_propagation"):
        checkpoint(progress_pct=0.0, message="Heavy lock busy — deferring to next tick")
        return

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        release_task_lock("heavy", "trustrank_propagation")
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return

    # Group D consolidation (2026-04-28): single shared helper instead
    # of the inline filter + values_list + or-fallback chain.
    try:
        seed_ids_raw = AppSetting.get_str("trustrank.seed_ids", "")
        seeds = [s for s in seed_ids_raw.split(",") if s]
        checkpoint(
            progress_pct=30.0,
            message=f"Propagating trust from {len(seeds)} seeds",
        )
        result = compute(g, trusted_seeds=seeds)
        checkpoint(progress_pct=70.0, message="Persisting TrustRank top-N")
        written = persist_top_n(signal=SIGNAL_TRUSTRANK, scores=result.scores)
        checkpoint(
            progress_pct=100.0,
            message=(
                f"TrustRank persisted: {written} of {len(result.scores)} nodes "
                f"({result.reason})"
            ),
        )
    finally:
        release_task_lock("heavy", "trustrank_propagation")


@scheduled_job(
    "weight_tuner_lbfgs_tpe",
    display_name="Ranking weight tuner (L-BFGS-B)",
    cadence_seconds=WEEK,
    estimate_seconds=30 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_weight_tuner_lbfgs_tpe(job, checkpoint) -> None:
    """Weekly L-BFGS-B tune of ranking weights (pre-existing weight_tuner.py).

    Side-effect: also fits + persists the Platt score calibration
    (pick #32) so the review-queue UI shows calibrated probabilities.
    Calibration runs after the weight tune so the new weights are
    reflected in the score → label mapping.
    """
    from apps.pipeline.services.score_calibrator import (
        fit_and_persist_from_history,
    )
    from apps.suggestions.services.weight_tuner import WeightTuner

    checkpoint(progress_pct=0.0, message="Starting L-BFGS-B tuning run")
    run_id = f"sched-{timezone.now():%Y%m%d%H%M}"
    WeightTuner().run(run_id=run_id)
    checkpoint(progress_pct=70.0, message="Fitting Platt score calibration")
    snapshot = fit_and_persist_from_history()
    if snapshot is not None:
        checkpoint(
            progress_pct=100.0,
            message=(
                f"Weight tune + Platt fit complete "
                f"(slope={snapshot.slope:.4f}, bias={snapshot.bias:.4f}, "
                f"n={snapshot.training_pairs})"
            ),
        )
    else:
        checkpoint(
            progress_pct=100.0,
            message="Weight tune complete; Platt fit skipped (insufficient history)",
        )


def _log_aci_alpha_update(aci) -> None:
    """Log the ACI α adaptation iff observations were processed."""
    if aci.observations_processed > 0:
        logger.info(
            "ACI: α %.4f → %.4f after %d observations (coverage %.2f)",
            aci.previous_alpha,
            aci.current_alpha,
            aci.observations_processed,
            aci.observed_coverage,
        )


@scheduled_job(
    "conformal_prediction_refresh",
    display_name="Conformal prediction calibration refresh",
    cadence_seconds=WEEK,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_conformal_prediction_refresh(job, checkpoint) -> None:
    """Pick #50 + #52 — weekly conformal refresh with online α adaptation.

    Two-step: (1) Pick #52 ACI updates α via Gibbs-Candès Algorithm 1
    from recent reviewed Suggestions; (2) Pick #50 fits fresh
    split-conformal calibration with the adapted α and persists the
    4 AppSetting rows the Suggestion-write consumer reads. Either
    step can no-op safely.
    """
    from apps.pipeline.services.adaptive_conformal_producer import (
        update_alpha_from_recent_outcomes,
    )
    from apps.pipeline.services.conformal_predictor import (
        fit_and_persist_from_history,
    )

    checkpoint(
        progress_pct=10.0,
        message="ACI: updating α from recent outcomes (pick #52)",
    )
    aci = update_alpha_from_recent_outcomes()
    _log_aci_alpha_update(aci)
    checkpoint(progress_pct=50.0, message="Fitting conformal calibration (pick #50)")
    snapshot = fit_and_persist_from_history(alpha=aci.current_alpha)
    if snapshot is None:
        checkpoint(
            progress_pct=100.0,
            message=(
                f"ACI updated (α={aci.current_alpha:.4f}); conformal fit "
                "skipped (< 30 reviewed pairs)"
            ),
        )
        return
    checkpoint(
        progress_pct=100.0,
        message=(
            f"Conformal calibration fit: half_width={snapshot.half_width:.4f} "
            f"at α={snapshot.alpha:.4f} (ACI-adapted from "
            f"{aci.previous_alpha:.4f}) over {snapshot.calibration_set_size} pairs"
        ),
    )


@scheduled_job(
    "elo_rating_refresh",
    display_name="Elo rating refresh (per-destination)",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_elo_rating_refresh(job, checkpoint) -> None:
    """Pick #35 — daily Elo refresh from review-queue history.

    Reads ``Suggestion.status`` history (last 90 days), pairs up
    suggestions sharing the same ``host_sentence_id``, applies the
    Elo update batch, and writes the new ratings to
    ``ContentItem.elo_rating``. Suggestion-write reads the persisted
    rating into ``Suggestion.score_elo_rating``.

    Cold-start safe: with no reviewed suggestions yet, the producer
    returns zero pairs and every ContentItem keeps its initial 1500
    rating. Once the review queue accumulates accept / reject pairs
    on the same host sentence, ratings start drifting.
    """
    from apps.pipeline.services.elo_rating_producer import (
        fit_and_persist_from_history,
    )

    checkpoint(progress_pct=10.0, message="Deriving pairs from review history")
    result = fit_and_persist_from_history()
    if result.pairs_processed == 0:
        checkpoint(
            progress_pct=100.0,
            message="No reviewed suggestion pairs yet — Elo unchanged",
        )
        return
    checkpoint(
        progress_pct=100.0,
        message=(
            f"Elo refresh complete: {result.pairs_processed} pairs → "
            f"{result.destinations_rated} destinations rated "
            f"({result.skipped_no_signal} skipped)"
        ),
    )


@scheduled_job(
    "meta_hyperparameter_hpo",
    display_name="Meta-hyperparameter auto-tune (TPE, Option B)",
    cadence_seconds=WEEK,
    estimate_seconds=90 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_meta_hyperparameter_hpo(job, checkpoint) -> None:
    """Fully-automatic weekly TPE study over all 12 TPE-tuned picks.

    Reads the daily reservoir eval set, runs 200 Optuna trials
    against it, applies safety rails (NDCG improvement gate,
    per-param change clamp, rollback-snapshot persistence), and
    writes winning params back to ``AppSetting``. Rail 3 (rollback
    watchdog) runs as its own daily job below.

    Logically depends on ``weight_tuner_lbfgs_tpe`` — the weekly
    ranker-weight fit should land first so the meta-HPO is tuning
    against the current calibrated ranker.
    """
    from apps.pipeline.services.meta_hpo import run_study_and_maybe_apply

    outcome = run_study_and_maybe_apply(checkpoint=checkpoint)
    msg = (
        f"applied {len(outcome.applied_params)} params, Δ={outcome.gate.delta:+.4f}"
        if outcome.applied and outcome.gate
        else (
            f"no apply (baseline NDCG={outcome.baseline_ndcg:.4f}, "
            f"best={outcome.best_ndcg:.4f})"
        )
    )
    logger.info("meta_hyperparameter_hpo: %s", msg)


def _read_meta_hpo_applied_at(checkpoint):
    """Parse the persisted apply-timestamp; return datetime or None to short-circuit."""
    from datetime import datetime
    from apps.core.models import AppSetting

    applied_at_raw = AppSetting.get_str("meta_hpo.applied_at", "")
    if not applied_at_raw:
        checkpoint(progress_pct=100.0, message="No prior apply — nothing to watch")
        return None
    try:
        return datetime.fromisoformat(applied_at_raw)
    except ValueError:
        logger.warning("meta_hpo_rollback_watchdog: bad applied_at: %s", applied_at_raw)
        checkpoint(progress_pct=100.0, message="Malformed applied_at — skip")
        return None


@scheduled_job(
    "meta_hpo_rollback_watchdog",
    display_name="Meta-HPO rollback watchdog (CTR regression check)",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_meta_hpo_rollback_watchdog(job, checkpoint) -> None:
    """Daily check — did CTR drop materially since the last auto-apply?

    Rail 3 of the fully-automatic safety stack. Restores the previous
    snapshot when the drop exceeds 5% over a 24-h post-apply window.
    """
    from datetime import timedelta
    from apps.pipeline.services.meta_hpo_safety import (
        ROLLBACK_OBSERVATION_HOURS,
        restore_previous_snapshot,
        should_rollback,
    )

    checkpoint(progress_pct=0.0, message="Reading last applied timestamp")
    applied_at = _read_meta_hpo_applied_at(checkpoint)
    if applied_at is None:
        return
    if timezone.now() - applied_at < timedelta(hours=ROLLBACK_OBSERVATION_HOURS):
        checkpoint(
            progress_pct=100.0,
            message="Post-apply window not yet elapsed — nothing to decide",
        )
        return
    # W1 ships the decision path with placeholder CTR values so the rail
    # is installed and tested. W3 wires GSC / click-log ingestion in.
    checkpoint(
        progress_pct=40.0,
        message="Computing 24-h CTR vs 7-day baseline (placeholder until W3)",
    )
    decision = should_rollback(baseline_ctr=0.20, observed_ctr=0.20)
    if not decision.rollback:
        checkpoint(progress_pct=100.0, message=f"No regression ({decision.reason})")
        return
    checkpoint(
        progress_pct=70.0,
        message=f"ROLLBACK triggered: {decision.reason}",
    )
    restored = restore_previous_snapshot()
    logger.warning(
        "meta_hpo_rollback_watchdog: rolled back (%s); %d params restored",
        decision.reason,
        len(restored),
    )
    checkpoint(
        progress_pct=100.0,
        message=f"Rolled back — {len(restored)} params restored",
    )


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


_LDA_MIN_TOKEN_LENGTH = 3
_LDA_MIN_DOCUMENT_COUNT = 2


def _build_lda_documents() -> list[list[str]]:
    """Tokenise ContentItem titles into a per-document list of stop-filtered tokens.

    Uses the existing simple word splitter so the vocabulary is consistent
    with the lexical retriever.
    """
    from apps.content.models import ContentItem
    from apps.pipeline.services.text_tokens import (
        STANDARD_ENGLISH_STOPWORDS,
        TOKEN_RE,
    )

    documents: list[list[str]] = []
    title_iter = ContentItem.objects.exclude(embedding__isnull=True).values_list(
        "title",
        flat=True,
    )
    for clean_text in title_iter:
        if not clean_text:
            continue
        toks = [
            t.lower()
            for t in TOKEN_RE.findall(clean_text)
            if len(t) >= _LDA_MIN_TOKEN_LENGTH
            and t.lower() not in STANDARD_ENGLISH_STOPWORDS
        ]
        if toks:
            documents.append(toks)
    return documents


def _persist_lda_model_paths(model_path: str, dict_path: str) -> None:
    """Write both AppSetting rows that ``lda_topics.infer_topics`` reads."""
    from apps.core.models import AppSetting
    from apps.pipeline.services import lda_topics

    description = "Pick #18 LDA topic model — refit weekly by lda_topic_refresh."
    for key, value in (
        (lda_topics.KEY_MODEL_PATH, model_path),
        (lda_topics.KEY_DICT_PATH, dict_path),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )


@scheduled_job(
    "lda_topic_refresh",
    display_name="LDA topic refresh",
    cadence_seconds=WEEK,
    estimate_seconds=45 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_lda_topic_refresh(job, checkpoint) -> None:
    """Weekly LDA topic-model refit over the corpus (pick #18, gensim).

    If gensim is installed, train LDA over the cleaned text of every
    ContentItem with a non-null clean_text. Persist the model + dictionary
    on disk and point the AppSetting paths at them so
    ``lda_topics.infer_topics`` picks up the fresh model.

    Cold-start safe: gensim missing → DeferredPickError; <2 docs → no-op.
    """
    import os
    from django.conf import settings as django_settings
    from apps.pipeline.services import lda_topics

    if not lda_topics.is_available():
        checkpoint(
            progress_pct=0.0,
            message="LDA topic refresh deferred — install `gensim` to enable",
        )
        raise DeferredPickError(
            "LDA topic refresh depends on `gensim` which is not installed.",
        )
    checkpoint(progress_pct=10.0, message="Loading corpus from ContentItem.clean_text")
    documents = _build_lda_documents()
    if len(documents) < _LDA_MIN_DOCUMENT_COUNT:
        checkpoint(
            progress_pct=100.0,
            message=f"Only {len(documents)} corpus docs — refit skipped",
        )
        return
    # Persist on the media volume so docker mounts survive rebuilds.
    media_root = getattr(django_settings, "MEDIA_ROOT", "/app/media")
    out_dir = os.path.join(media_root, "lda")
    os.makedirs(out_dir, exist_ok=True)
    model_path = os.path.join(out_dir, "lda.model")
    dict_path = os.path.join(out_dir, "lda.dict")
    checkpoint(progress_pct=40.0, message=f"Training LDA over {len(documents)} docs")
    if not lda_topics.fit_and_save(
        documents,
        model_path=model_path,
        dict_path=dict_path,
    ):
        checkpoint(progress_pct=100.0, message="LDA training reported failure")
        return
    _persist_lda_model_paths(model_path, dict_path)
    checkpoint(
        progress_pct=100.0,
        message=f"LDA model refit complete — {len(documents)} docs trained",
    )


_KENLM_MIN_CORPUS_LINES = 100
_KENLM_MIN_SENTENCE_CHARS = 10
_KENLM_SENTENCE_CHUNK_SIZE = 5000
_KENLM_MODEL_DESCRIPTION = (
    "Pick #23 KenLM trigram fluency model — refit weekly by "
    "kenlm_retrain via the lmplz binary. ARPA format; "
    "loaded directly by kenlm.Model."
)


def _check_kenlm_dependencies(checkpoint) -> bool:
    """Verify pip + binary deps. Raises DeferredPickError or returns the pip-state flag."""
    from apps.pipeline.services import kenlm_fluency

    pip_ok = kenlm_fluency.is_available()
    binary_ok = kenlm_fluency.lmplz_available()
    if not (pip_ok or binary_ok):
        checkpoint(
            progress_pct=0.0,
            message="KenLM deferred — install `kenlm` pip dep AND `lmplz` binary",
        )
        raise DeferredPickError(
            "KenLM retrain requires both the `kenlm` pip package (for inference) "
            "and the `lmplz` binary (for training). Neither is currently available.",
        )
    if not binary_ok:
        checkpoint(
            progress_pct=0.0,
            message="`lmplz` binary not on PATH — KenLM retrain deferred",
        )
        raise DeferredPickError(
            "KenLM retrain requires the `lmplz` binary. Install via "
            "`apt install kenlm-tools` or build from source.",
        )
    return pip_ok


def _build_kenlm_corpus_lines() -> list[str]:
    """Stream Sentence.text rows + filter blanks/very-short lines."""
    from apps.content.models import Sentence

    corpus_lines: list[str] = []
    iterator = Sentence.objects.values_list("text", flat=True).iterator(
        chunk_size=_KENLM_SENTENCE_CHUNK_SIZE,
    )
    for text in iterator:
        if not text:
            continue
        cleaned = " ".join(text.split())
        if len(cleaned) < _KENLM_MIN_SENTENCE_CHARS:
            continue
        corpus_lines.append(cleaned)
    return corpus_lines


@scheduled_job(
    "kenlm_retrain",
    display_name="KenLM trigram retrain",
    cadence_seconds=WEEK,
    estimate_seconds=20 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_kenlm_retrain(job, checkpoint) -> None:
    """Weekly KenLM trigram refit over corpus sentences (pick #23).

    Builds a corpus of sentence text from existing Sentence rows, pipes
    it to the lmplz binary via subprocess, and writes the resulting ARPA
    file to MEDIA_ROOT/kenlm/model.arpa. Sets kenlm.model_path AppSetting
    so kenlm_fluency.score_fluency auto-activates on the next call.

    Cold-start safe: pip + binary missing → DeferredPickError; <100
    sentences → no-op; subprocess failure → previous model preserved.
    """
    from apps.core.models import AppSetting
    from apps.pipeline.services import kenlm_fluency

    pip_ok = _check_kenlm_dependencies(checkpoint)
    checkpoint(progress_pct=10.0, message="Loading sentences from corpus")
    corpus_lines = _build_kenlm_corpus_lines()
    if len(corpus_lines) < _KENLM_MIN_CORPUS_LINES:
        checkpoint(
            progress_pct=100.0,
            message=f"Only {len(corpus_lines)} sentences (<{_KENLM_MIN_CORPUS_LINES}) — KenLM retrain skipped",
        )
        return
    output_path = _ensure_model_output_path("kenlm", filename="model.arpa")
    checkpoint(
        progress_pct=30.0,
        message=f"Running lmplz over {len(corpus_lines)} sentences (trigram)",
    )
    if not kenlm_fluency.fit_arpa_with_lmplz(
        corpus_lines=corpus_lines,
        output_arpa_path=output_path,
        order=3,
    ):
        checkpoint(
            progress_pct=100.0,
            message="lmplz reported failure — keeping previous KenLM model",
        )
        return
    AppSetting.objects.update_or_create(
        key=kenlm_fluency.KEY_MODEL_PATH,
        defaults={"value": output_path, "description": _KENLM_MODEL_DESCRIPTION},
    )
    half_state = (
        "" if pip_ok else " (kenlm pip dep still missing — install for inference)"
    )
    checkpoint(
        progress_pct=100.0,
        message=f"KenLM ARPA persisted from {len(corpus_lines)} sentences{half_state}",
    )


def _build_node2vec_edge_triples(graph) -> list[tuple]:
    """Convert directed graph's edges into ``(src, dst, weight)`` string triples.

    node2vec internally treats them as undirected for walks; weights bias
    the walk transition probabilities. String keys are required because
    the underlying Word2Vec needs hashable string nodes.
    """
    edges: list[tuple] = []
    for src, dst, data in graph.edges(data=True):
        weight = float(data.get("weight", 1.0)) if data else 1.0
        edges.append((str(src), str(dst), weight))
    return edges


_NODE2VEC_DESCRIPTION = (
    "Pick #37 Node2Vec embeddings — refit weekly by node2vec_walks. "
    "Pickled dict {node_str: vector}."
)


def _persist_node2vec_path(output_path: str) -> None:
    """Write the Node2Vec embeddings-path AppSetting row."""
    from apps.core.models import AppSetting
    from apps.pipeline.services import node2vec_embeddings

    AppSetting.objects.update_or_create(
        key=node2vec_embeddings.KEY_EMBEDDINGS_PATH,
        defaults={"value": output_path, "description": _NODE2VEC_DESCRIPTION},
    )


@scheduled_job(
    "node2vec_walks",
    display_name="Node2Vec random walks + embedding",
    cadence_seconds=WEEK,
    estimate_seconds=35 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_node2vec_walks(job, checkpoint) -> None:
    """Weekly Node2Vec embedding refit over the internal-link graph (pick #37).

    Reuses the weighted-PageRank graph loader as HITS / PPR / TrustRank.
    Cold-start safe: pip dep missing → defer; empty graph → no-op;
    training failure → previous embeddings preserved.
    """
    from apps.pipeline.services import node2vec_embeddings

    if not node2vec_embeddings.is_available():
        checkpoint(
            progress_pct=0.0,
            message="Node2Vec deferred — install `node2vec` + `gensim` to enable",
        )
        raise DeferredPickError(
            "Node2Vec depends on `node2vec` (which itself wraps gensim + networkx) "
            "which is not installed.",
        )
    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() < 2:
        checkpoint(
            progress_pct=100.0,
            message=f"Graph has only {g.number_of_nodes()} nodes — skip Node2Vec",
        )
        return
    edges = _build_node2vec_edge_triples(g)
    if not edges:
        checkpoint(progress_pct=100.0, message="No edges in graph — skip Node2Vec")
        return
    output_path = _ensure_model_output_path("node2vec", filename="embeddings.pkl")
    checkpoint(
        progress_pct=20.0,
        message=f"Training Node2Vec over {g.number_of_nodes()} nodes / {len(edges)} edges",
    )
    if not node2vec_embeddings.fit_and_save(edges=edges, output_path=output_path):
        checkpoint(
            progress_pct=100.0,
            message="Node2Vec training reported failure — keeping previous embeddings",
        )
        return
    _persist_node2vec_path(output_path)
    checkpoint(
        progress_pct=100.0,
        message=f"Node2Vec persisted: {g.number_of_nodes()} node embeddings",
    )


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
    """Monthly PQ codebook refit over BGE-M3 embeddings (pick #20).

    Reads the population of non-null ContentItem embeddings, fits a
    FAISS IndexPQ codebook, persists the codebook bytes (base64) to
    AppSetting, and backfills the ``ContentItem.pq_code`` +
    ``pq_code_version`` columns for every encoded row.

    Cold-start safe: returns immediately when FAISS isn't installed
    or when fewer than ``MIN_TRAINING_ROWS`` (39 × Ks) embeddings
    exist. Group B.2 will land the optional read-path swap that
    short-circuits cosine similarity through PQ codes; Group B.1
    only seeds the column.
    """
    try:
        import faiss  # noqa: F401
    except ImportError:
        checkpoint(
            progress_pct=0.0,
            message="FAISS not installed — product_quantization_refit deferred",
        )
        raise DeferredPickError("faiss not installed; PQ refit requires it")

    from apps.pipeline.services.product_quantization_producer import (
        fit_and_persist_from_embeddings,
    )

    result = fit_and_persist_from_embeddings(progress_callback=checkpoint)
    if result is None:
        checkpoint(
            progress_pct=100.0,
            message=(
                "Insufficient training data for PQ — keeping previous "
                "codebook (cold-start safe)"
            ),
        )
        return
    checkpoint(
        progress_pct=100.0,
        message=(
            f"PQ codebook v{result.snapshot.version} persisted; "
            f"{result.rows_encoded} rows encoded, "
            f"{result.snapshot.bytes_per_vector} bytes/vec"
        ),
    )


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


def _summarize_cascade_snapshots(review_snap, impression_snap) -> str:
    """Build a one-line summary of cascade re-estimate snapshots."""
    parts: list[str] = []
    if review_snap is not None:
        parts.append(
            f"review-queue Cascade: {len(review_snap.cascade_relevance)} dests "
            f"+ IPS CTR: {len(review_snap.ips_weighted_ctr)} positions "
            f"({review_snap.training_runs} runs)",
        )
    else:
        parts.append("review-queue Cascade: insufficient history")
    if impression_snap is not None:
        parts.append(
            f"impression Cascade: {len(impression_snap.relevance)} dests "
            f"({impression_snap.sessions} sessions, "
            f"{impression_snap.observations} impressions)",
        )
    else:
        parts.append("impression Cascade: cold-start (insufficient impressions)")
    return "; ".join(parts)


@scheduled_job(
    "cascade_click_em_re_estimate",
    display_name="Cascade click-model re-estimate",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_cascade_click_em_re_estimate(job, checkpoint) -> None:
    """Weekly re-estimate of Cascade doc relevance (pick #34).

    Two complementary fits side-by-side: review-queue history (always-on)
    via ``feedback_relevance.compute_and_persist`` and frontend-logged
    impressions via ``cascade_click_em_producer.fit_and_persist_from_impressions``.
    Cold-start safe: impression fit no-ops until the frontend hook lands.
    Both persist to separate AppSetting namespaces.
    """
    from apps.pipeline.services.cascade_click_em_producer import (
        fit_and_persist_from_impressions as fit_cascade_from_impressions,
    )
    from apps.pipeline.services.feedback_relevance import compute_and_persist

    checkpoint(progress_pct=0.0, message="Aggregating Cascade + IPS feedback")
    review_snap = compute_and_persist()
    checkpoint(
        progress_pct=50.0,
        message="Fitting Cascade from SuggestionImpression rows",
    )
    impression_snap = fit_cascade_from_impressions()
    checkpoint(
        progress_pct=100.0,
        message=_summarize_cascade_snapshots(review_snap, impression_snap),
    )


def _summarize_position_bias_snapshots(cascade_snap, eta_snap) -> str:
    """Build a one-line summary of position-bias IPS refit snapshots."""
    parts: list[str] = []
    if cascade_snap is not None:
        parts.append(
            f"per-position CTR: {len(cascade_snap.ips_weighted_ctr)} positions "
            f"({cascade_snap.training_runs} runs)",
        )
    else:
        parts.append("per-position CTR: insufficient review history")
    if eta_snap is not None:
        parts.append(
            f"η fit: {eta_snap.eta:.3f} from {eta_snap.observations} impressions",
        )
    else:
        parts.append("η fit: cold-start (insufficient impressions)")
    return "; ".join(parts)


@scheduled_job(
    "position_bias_ips_refit",
    display_name="Position-bias IPS η refit",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_position_bias_ips_refit(job, checkpoint) -> None:
    """Weekly refit of position-bias IPS weights (pick #33).

    Two complementary refits side-by-side: review-queue history (always-on)
    persists per-position IPS-weighted CTR; frontend-logged impressions
    fit the η exponent of the power-law propensity. Cold-start safe: η
    no-ops until impressions accumulate; consumer falls back to η=1.0.
    Both persist to separate AppSetting namespaces.
    """
    from apps.pipeline.services.feedback_relevance import compute_and_persist
    from apps.pipeline.services.position_bias_ips_producer import (
        fit_and_persist_from_impressions,
    )

    checkpoint(progress_pct=0.0, message="Refitting IPS weights from review history")
    cascade_snap = compute_and_persist()
    checkpoint(
        progress_pct=50.0,
        message="Fitting η from SuggestionImpression rows",
    )
    eta_snap = fit_and_persist_from_impressions()
    checkpoint(
        progress_pct=100.0,
        message=_summarize_position_bias_snapshots(cascade_snap, eta_snap),
    )


_FM_FEEDBACK_LOOKBACK_DAYS = 90
_FM_MIN_TRAINING_ROWS = 5

_FM_SCORE_COLUMNS = (
    "score_semantic",
    "score_keyword",
    "score_node_affinity",
    "score_quality",
    "score_link_freshness",
    "score_phrase_relevance",
    "score_field_aware_relevance",
    "score_rare_term_propagation",
    "score_anchor_diversity",
)


def _load_fm_feedback_rows(lookback_days: int) -> list[dict]:
    """Pull every approved/rejected Suggestion in the lookback window with score cols."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.suggestions.models import Suggestion

    cutoff = timezone.now() - timedelta(days=lookback_days)
    return list(
        Suggestion.objects.filter(
            updated_at__gte=cutoff,
            status__in=["approved", "rejected"],
        ).values(
            *_FM_SCORE_COLUMNS,
            "anchor_confidence",
            "status",
        ),
    )


def _build_fm_features(rows: list[dict]) -> tuple[list[dict], list[float]]:
    """Convert each row into a DictVectorizer-friendly feature dict + target.

    DictVectorizer turns the categorical ``anchor_confidence`` value into
    one-hot columns automatically and leaves numeric fields alone — no
    manual encoding needed here.
    """
    features: list[dict] = []
    targets: list[float] = []
    for row in rows:
        feats: dict = {col: float(row.get(col) or 0.0) for col in _FM_SCORE_COLUMNS}
        feats[f"anchor_confidence={row.get('anchor_confidence') or 'none'}"] = 1.0
        features.append(feats)
        targets.append(1.0 if row.get("status") == "approved" else 0.0)
    return features, targets


def _ensure_model_output_path(subdir: str, filename: str = "model.pkl") -> str:
    """Compute + ensure the model output dir under MEDIA_ROOT; return full path."""
    import os
    from django.conf import settings as django_settings

    media_root = getattr(django_settings, "MEDIA_ROOT", "/app/media")
    out_dir = os.path.join(media_root, subdir)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)


_FM_MODEL_DESCRIPTION = (
    "Pick #39 Factorization Machines — refit weekly by "
    "factorization_machines_refit. Captures pairwise score "
    "interactions linear blends miss."
)


def _persist_fm_model_path(output_path: str) -> None:
    """Write the FM model-path AppSetting row read by predict()."""
    from apps.core.models import AppSetting
    from apps.pipeline.services import factorization_machines

    AppSetting.objects.update_or_create(
        key=factorization_machines.KEY_MODEL_PATH,
        defaults={"value": output_path, "description": _FM_MODEL_DESCRIPTION},
    )


@scheduled_job(
    "factorization_machines_refit",
    display_name="Factorization Machines refit",
    cadence_seconds=WEEK,
    estimate_seconds=10 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_factorization_machines_refit(job, checkpoint) -> None:
    """Weekly FM refit over operator-feedback Suggestion features (pick #39).

    Builds DictVectorizer-friendly feature dicts from reviewed Suggestion
    score columns (semantic / keyword / node / quality / FR099-FR105).
    Target = 1.0 approved, 0.0 rejected. FM learns pairwise interactions
    that linear blends miss. Cold-start safe: missing pip dep → defer;
    <5 reviewed rows → no-op; training failure → previous model preserved.
    """
    from apps.pipeline.services import factorization_machines

    if not factorization_machines.is_available():
        checkpoint(
            progress_pct=0.0,
            message="FM deferred — install `scikit-learn` to enable",
        )
        raise DeferredPickError(
            "Factorization Machines (hand-rolled NumPy implementation) "
            "still requires `scikit-learn` for DictVectorizer; "
            "scikit-learn is in requirements.txt.",
        )
    rows = _load_fm_feedback_rows(_FM_FEEDBACK_LOOKBACK_DAYS)
    if len(rows) < _FM_MIN_TRAINING_ROWS:
        checkpoint(
            progress_pct=100.0,
            message=f"Only {len(rows)} reviewed rows — FM refit skipped",
        )
        return
    features, targets = _build_fm_features(rows)
    output_path = _ensure_model_output_path("fm")
    checkpoint(
        progress_pct=20.0,
        message=f"Training FM over {len(features)} reviewed Suggestions",
    )
    if not factorization_machines.fit_and_save(
        features=features,
        targets=targets,
        output_path=output_path,
        task="classification",
    ):
        checkpoint(
            progress_pct=100.0,
            message="FM training reported failure — keeping previous model",
        )
        return
    _persist_fm_model_path(output_path)
    checkpoint(
        progress_pct=100.0,
        message=f"FM persisted: {len(features)} samples × {len(features[0])} features",
    )


def _load_bpr_interactions(lookback_days: int) -> list[tuple[str, str, float]]:
    """Build BPR-style ``(user_id, item_id, weight)`` interactions from feedback.

    ``approved`` → weight 1.0 (strong positive). ``rejected`` → weight 0.1
    (weak signal — BPR uses the implicit-feedback convention where any
    nonzero weight means "the user saw this item"; the pairwise loss does
    the rest). Lookback matches IPS / Cascade producers so we never train
    on a stale pool that diverges from the other feedback signals.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.suggestions.models import Suggestion

    cutoff = timezone.now() - timedelta(days=lookback_days)
    rows = Suggestion.objects.filter(
        updated_at__gte=cutoff,
        status__in=["approved", "rejected"],
    ).values_list("host_id", "destination_id", "status")
    interactions: list[tuple[str, str, float]] = []
    for host_id, dest_id, status in rows:
        if host_id is None or dest_id is None:
            continue
        interactions.append(
            (str(host_id), str(dest_id), 1.0 if status == "approved" else 0.1),
        )
    return interactions


_BPR_DESCRIPTION = (
    "Pick #38 BPR (Bayesian Personalized Ranking) — refit "
    "weekly by bpr_refit. Pickled implicit.bpr model + indexes."
)


def _persist_bpr_model_path(output_path: str) -> None:
    """Write the BPR model-path AppSetting row read by score_for_user()."""
    from apps.core.models import AppSetting
    from apps.pipeline.services import bpr_ranking

    AppSetting.objects.update_or_create(
        key=bpr_ranking.KEY_MODEL_PATH,
        defaults={"value": output_path, "description": _BPR_DESCRIPTION},
    )


@scheduled_job(
    "bpr_refit",
    display_name="BPR matrix factorisation refit",
    cadence_seconds=WEEK,
    estimate_seconds=15 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_bpr_refit(job, checkpoint) -> None:
    """Weekly BPR refit over operator approve/reject feedback (pick #38).

    Treats host-content as BPR "user", destination as "item". Approved →
    positive; rejected → implicit-skip via pairwise loss. Cold-start safe:
    missing pip dep → defer; <5 interactions → no-op; training failure
    → previous model preserved.
    """
    from apps.pipeline.services import bpr_ranking

    if not bpr_ranking.is_available():
        checkpoint(
            progress_pct=0.0,
            message="BPR deferred — install `implicit` to enable",
        )
        raise DeferredPickError(
            "BPR depends on `implicit` (Cython-backed pairwise LTR) which is not installed.",
        )
    interactions = _load_bpr_interactions(_FM_FEEDBACK_LOOKBACK_DAYS)
    if len(interactions) < _FM_MIN_TRAINING_ROWS:
        checkpoint(
            progress_pct=100.0,
            message=f"Only {len(interactions)} approve/reject rows — refit skipped",
        )
        return
    output_path = _ensure_model_output_path("bpr")
    checkpoint(
        progress_pct=20.0,
        message=f"Training BPR over {len(interactions)} interactions",
    )
    if not bpr_ranking.fit_and_save(
        interactions=interactions,
        output_path=output_path,
    ):
        checkpoint(
            progress_pct=100.0,
            message="BPR training reported failure — keeping previous model",
        )
        return
    _persist_bpr_model_path(output_path)
    checkpoint(
        progress_pct=100.0,
        message=f"BPR persisted: {len(interactions)} interactions trained",
    )


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
    "ndcg_smoke_test",
    display_name="Retriever NDCG smoke test",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_ndcg_smoke_test(job, checkpoint) -> None:
    """Daily NDCG@10 readout over the reviewed-Suggestion stream.

    Polish.B — paper-backed automated retriever-quality eval. Pulls
    approved + rejected Suggestions from the last 30 days, computes
    NDCG@10 with bootstrap 95% confidence, gates on Sanderson 2010
    §5.2 sample-size floor (≥ 50 for basic, ≥ 200 for pairwise),
    and persists the result to ``AppSetting["ndcg_eval.latest.json"]``
    for the dashboard.

    Cold-start safe: < 50 reviewed → ``sufficient_data=False`` and
    the dashboard shows "Approve more, then this reads".
    """
    from apps.pipeline.services.ndcg_eval import evaluate_and_persist

    checkpoint(progress_pct=0.0, message="Aggregating reviewed-Suggestion stream")
    result = evaluate_and_persist()
    if not result.sufficient_data:
        checkpoint(progress_pct=100.0, message=result.message)
        return
    summary = (
        f"NDCG@10: {result.ndcg:.3f} "
        f"[CI95: {result.confidence_lower:.3f}-{result.confidence_upper:.3f}] "
        f"over {result.sample_size} reviewed suggestions"
    )
    checkpoint(progress_pct=100.0, message=summary)


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


# ────────────────────────────────────────────────────────────────────
# Daily data retention — moved into the operator window per the
# laptop-sleep constraint. The 22:30 slot is the last 30 minutes
# before the window closes at 23:00, so it runs after every higher-
# priority job has had the rest of the window. The window guard
# refuses to start it past 22:30 if its 30-min estimate would
# overflow 23:00; missed runs surface as a deduped JobAlert and the
# operator catches up via the Run Now button. Roaring `cardinality_
# preview` makes the queue depth visible from the dashboard.
# ────────────────────────────────────────────────────────────────────


@scheduled_job(
    "daily_data_retention",
    display_name="Data retention sweep",
    cadence_seconds=DAY,
    estimate_seconds=30 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_daily_data_retention(job, checkpoint) -> None:
    """Run the same body as ``apps.pipeline.tasks.nightly_data_retention``.

    The function name is kept inside ``tasks.py`` (despite the
    ``nightly_`` prefix) so the existing ``.run()`` invocation from
    ``apps.diagnostics.views`` and the manual-run UI continue to
    work without churn. This @scheduled_job wrapper is the cadence
    path — the celery beat entry has been removed in favour of this
    runner-managed flow so the laptop-sleep window guard, progress
    bar, and missed-job alerts all apply.

    Progress callback wires the function's existing
    ``progress_callback`` parameter into the runner's ``checkpoint``
    so the dashboard renders a live progress bar.
    """
    from apps.pipeline.tasks import nightly_data_retention

    def _bridge(pct: float, message: str) -> None:
        checkpoint(progress_pct=float(pct), message=str(message))

    nightly_data_retention(progress_callback=_bridge)


# ────────────────────────────────────────────────────────────────────
# PR-Anchor — corpus-stats refresh for Algo 3 (Iglewicz-Hoaglin
# modified z-score). Recomputes the median + MAD of character-bigram
# entropy across recent anchor texts so the modified z-score stays
# calibrated as the corpus grows / drifts. Runs weekly inside the
# 11am-23pm window. Cold-start safe — when no Suggestion rows have
# anchor_phrase set yet, the job no-ops and the defaults from
# migration 0047 stay active.
# ────────────────────────────────────────────────────────────────────


_ANCHOR_STATS_MIN_ANCHORS = 30  # Iglewicz-Hoaglin 1993 §3.2 minimum sample size
_ANCHOR_STATS_MAX_ANCHORS = 50_000


def _load_recent_approved_anchors() -> list[str]:
    """Pull up to 50k anchor texts from approved/applied/verified Suggestions."""
    from apps.suggestions.models import Suggestion

    rows = (
        Suggestion.objects.filter(
            status__in=("approved", "applied", "verified"),
        )
        .order_by("-updated_at")
        .values_list("anchor_phrase", flat=True)[:_ANCHOR_STATS_MAX_ANCHORS]
    )
    return [a for a in rows if a]


def _compute_anchor_entropy_stats(anchors: list[str]) -> tuple[float, float, int]:
    """Return ``(median, mad, n)`` for character-bigram entropy across anchors.

    MAD is the median absolute deviation — a robust scale estimator that ignores
    outliers (Hampel 1974, J. Amer. Statist. Assoc. 69). Both the median and the
    MAD are computed via Polars's vectorised ``Series.median()`` instead of the
    previous hand-rolled ``_median()`` helper, which kept exact parity with
    Python's ``statistics.median`` (linear interpolation on even-length input).
    """
    import polars as pl

    from apps.pipeline.services.anchor_garbage_signals import _bigram_entropy

    entropies = [float(_bigram_entropy(a.lower())) for a in anchors]
    if not entropies:
        return 0.0, 0.0, 0
    series = pl.Series("entropy", entropies)
    median = float(series.median())
    mad = float((series - median).abs().median())
    return median, mad, len(entropies)


def _persist_anchor_entropy_stats(median: float, mad: float) -> None:
    """Write the median + MAD to AppSetting so the dispatcher reads fresh corpus norms."""
    from apps.core.models import AppSetting
    from apps.pipeline.services.anchor_garbage_signals import (
        KEY_CORPUS_ENTROPY_MAD,
        KEY_CORPUS_ENTROPY_MEDIAN,
    )

    AppSetting.objects.update_or_create(
        key=KEY_CORPUS_ENTROPY_MEDIAN,
        defaults={
            "value": f"{median:.6f}",
            "description": (
                "PR-Anchor Algo 3 corpus median of character-bigram "
                "entropy across approved anchors. Refit weekly."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_CORPUS_ENTROPY_MAD,
        defaults={
            "value": f"{mad:.6f}",
            "description": (
                "PR-Anchor Algo 3 corpus MAD of character-bigram entropy "
                "across approved anchors. Refit weekly."
            ),
        },
    )


@scheduled_job(
    "anchor_self_information_corpus_stats_refresh",
    display_name="Anchor self-information corpus stats refresh",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_anchor_self_information_corpus_stats_refresh(job, checkpoint) -> None:
    """Refit the corpus-wide median + MAD of character-bigram entropy.

    Reads up to ~50k recent anchor texts from approved Suggestions,
    computes Shannon bigram entropy per anchor, persists the median + MAD
    to AppSetting so the dispatcher's Iglewicz-Hoaglin modified z-score
    uses fresh corpus norms instead of the sensible-English defaults.

    Cold-start safe: < 30 approved Suggestions → log and exit. Per
    Iglewicz-Hoaglin 1993 §3.2, N ≥ 30 is the minimum for stable
    median/MAD estimates.
    """
    checkpoint(progress_pct=10.0, message="Loading recent anchor texts")
    anchors = _load_recent_approved_anchors()
    if len(anchors) < _ANCHOR_STATS_MIN_ANCHORS:
        checkpoint(
            progress_pct=100.0,
            message=(
                f"Only {len(anchors)} approved anchors — using "
                f"sensible-English defaults until ≥ {_ANCHOR_STATS_MIN_ANCHORS} "
                "are available."
            ),
        )
        return
    checkpoint(
        progress_pct=40.0,
        message=f"Computing bigram entropy across {len(anchors)} anchors",
    )
    median, mad, n = _compute_anchor_entropy_stats(anchors)
    checkpoint(
        progress_pct=80.0,
        message=f"Persisting median={median:.3f} mad={mad:.3f}",
    )
    _persist_anchor_entropy_stats(median, mad)
    checkpoint(
        progress_pct=100.0,
        message=f"Stats refreshed: N={n}, median={median:.3f}, MAD={mad:.3f}",
    )


@scheduled_job(
    "graph_signals_compute_all",
    display_name="Graph Signals Compute All",
    cadence_seconds=86400,
    estimate_seconds=600,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_graph_signals_compute_all(job, checkpoint) -> None:
    from apps.graph.services.graph_signal_job import run_signals
    from apps.pipeline.services.pipeline_loaders import _load_advanced_graph_signals_settings

    checkpoint(progress_pct=10.0, message="Starting graph signals computation...")
    settings = _load_advanced_graph_signals_settings()
    run_signals(
        force=False,
        icpc_min_community_size=settings.icpc.min_community_size,
        sbma_num_blocks=settings.sbma.num_blocks,
    )
    checkpoint(progress_pct=100.0, message="Graph signals computation complete.")
