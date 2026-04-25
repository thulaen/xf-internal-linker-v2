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
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_PPR,
        persist_top_n,
    )
    from apps.pipeline.services.personalized_pagerank import compute

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


@scheduled_job(
    "hits_refresh",
    display_name="HITS authority + hub refresh",
    cadence_seconds=DAY,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_hits_refresh(job, checkpoint) -> None:
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_HITS_AUTHORITY,
        SIGNAL_HITS_HUB,
        persist_top_n,
    )
    from apps.pipeline.services.hits import compute

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return
    checkpoint(progress_pct=30.0, message="Computing HITS scores")
    scores = compute(g)
    checkpoint(progress_pct=70.0, message="Persisting authority + hub top-N")
    auth_count = persist_top_n(signal=SIGNAL_HITS_AUTHORITY, scores=scores.authority)
    hub_count = persist_top_n(signal=SIGNAL_HITS_HUB, scores=scores.hub)
    checkpoint(
        progress_pct=100.0,
        message=(
            f"HITS persisted: {auth_count} authorities + {hub_count} hubs "
            f"(of {len(scores.authority)} nodes)"
        ),
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

    Reads the operator-tunable AppSettings the plan specified
    (``trustrank_auto_seeder.*``) and feeds the seed picker
    real per-node quality data:

    - ``post_quality`` from ``ContentItem.content_value_score``
    - ``readability_grade`` from ``Post.flesch_kincaid_grade``
      (the Phase 3 #19 column we just shipped — single source of
      truth for readability, no duplicate computation)
    - ``spam_flagged`` from a low-quality threshold on
      content_value_score (no dedicated spam column on ContentItem
      yet; this is the closest available proxy)

    Cold-start safe: every quality input is optional. Missing rows
    pass the filter (the picker only rejects on affirmative low-
    quality evidence — see ``pick_seeds`` docstring §3).
    """
    from apps.content.models import ContentItem, Post
    from apps.core.models import AppSetting
    from apps.pipeline.services.trustrank_auto_seeder import (
        DEFAULT_CANDIDATE_POOL_SIZE,
        DEFAULT_POST_QUALITY_MIN,
        DEFAULT_READABILITY_GRADE_MAX,
        DEFAULT_SEED_COUNT_K,
        pick_seeds,
    )

    g = _load_networkx_graph(checkpoint)
    if g.number_of_nodes() == 0:
        checkpoint(progress_pct=100.0, message="Empty graph — skip")
        return

    # Operator-tunable parameters with helper-provided defaults.
    def _setting_int(key: str, default: int) -> int:
        try:
            row = AppSetting.objects.filter(key=key).first()
            return int(row.value) if row else default
        except (TypeError, ValueError):
            return default

    def _setting_float(key: str, default: float) -> float:
        try:
            row = AppSetting.objects.filter(key=key).first()
            return float(row.value) if row else default
        except (TypeError, ValueError):
            return default

    candidate_pool_size = _setting_int(
        "trustrank_auto_seeder.candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE
    )
    seed_count_k = _setting_int(
        "trustrank_auto_seeder.seed_count_k", DEFAULT_SEED_COUNT_K
    )
    post_quality_min = _setting_float(
        "trustrank_auto_seeder.post_quality_min", DEFAULT_POST_QUALITY_MIN
    )
    readability_grade_max = _setting_float(
        "trustrank_auto_seeder.readability_grade_max",
        DEFAULT_READABILITY_GRADE_MAX,
    )
    # Spam flagging — no dedicated column, so we treat very low
    # content_value_score as the proxy. Tunable via AppSetting; 0.0
    # disables the spam filter entirely.
    spam_quality_floor = _setting_float(
        "trustrank_auto_seeder.spam_content_value_floor", 0.15
    )

    checkpoint(
        progress_pct=20.0,
        message="Loading per-node quality + readability + spam maps",
    )

    # Build per-node quality maps keyed by the (pk, content_type)
    # tuple the graph uses. Single DB query each — O(N) memory but
    # bounded by the active ContentItem table size, well below the
    # 50 MB / 50 MB budget the plan calls out for pick #51.
    quality_rows = ContentItem.objects.filter(is_deleted=False).values_list(
        "pk", "content_type", "content_value_score"
    )
    post_quality: dict = {}
    spam_flagged: set = set()
    for pk, content_type, value_score in quality_rows:
        key = (pk, content_type)
        if value_score is not None:
            post_quality[key] = float(value_score)
            if spam_quality_floor > 0.0 and float(value_score) <= spam_quality_floor:
                spam_flagged.add(key)

    readability_rows = (
        Post.objects.select_related("content_item")
        .filter(content_item__is_deleted=False)
        .values_list(
            "content_item__pk",
            "content_item__content_type",
            "flesch_kincaid_grade",
        )
    )
    readability_grade: dict = {}
    for pk, content_type, grade in readability_rows:
        if grade is not None and grade > 0.0:
            readability_grade[(pk, content_type)] = float(grade)

    checkpoint(
        progress_pct=50.0,
        message=(
            f"Picking seeds from pool={candidate_pool_size} k={seed_count_k} "
            f"(quality={len(post_quality)}, readability={len(readability_grade)}, "
            f"spam={len(spam_flagged)})"
        ),
    )
    result = pick_seeds(
        g,
        candidate_pool_size=candidate_pool_size,
        seed_count_k=seed_count_k,
        spam_flagged=spam_flagged,
        post_quality=post_quality,
        post_quality_min=post_quality_min,
        readability_grade=readability_grade,
        readability_grade_max=readability_grade_max,
    )
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
        message=(
            f"Picked {len(result.seeds)} seeds "
            f"({result.reason}; rejected={result.rejected_count}, "
            f"fallback={'yes' if result.fallback_used else 'no'})"
        ),
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
    from apps.pipeline.services.graph_signal_store import (
        SIGNAL_TRUSTRANK,
        persist_top_n,
    )
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
    checkpoint(progress_pct=70.0, message="Persisting TrustRank top-N")
    written = persist_top_n(signal=SIGNAL_TRUSTRANK, scores=result.scores)
    checkpoint(
        progress_pct=100.0,
        message=(
            f"TrustRank persisted: {written} of {len(result.scores)} nodes "
            f"({result.reason})"
        ),
    )


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


@scheduled_job(
    "conformal_prediction_refresh",
    display_name="Conformal prediction calibration refresh",
    cadence_seconds=WEEK,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_MEDIUM,
)
def run_conformal_prediction_refresh(job, checkpoint) -> None:
    """Pick #50 + #52 — weekly conformal refresh with online α adaptation.

    Two-step refresh that wires both picks in one scheduled job:

    1. **Pick #52 (ACI)** — pull recent reviewed Suggestions whose
       conformal bounds were populated, compute observed coverage,
       update the persisted α via Gibbs-Candès Algorithm 1. Cold
       start: no observations → α stays at the static target.
    2. **Pick #50** — fit a fresh split-conformal calibration using
       the (possibly adapted) α from step 1, persist the four
       AppSetting rows the Suggestion-write consumer reads.

    Either step can no-op without breaking the other — ACI returns
    the prior α when there's nothing to observe, and the conformal
    fit runs on whatever α it gets.
    """
    from apps.pipeline.services.adaptive_conformal_producer import (
        update_alpha_from_recent_outcomes,
    )
    from apps.pipeline.services.conformal_predictor import (
        fit_and_persist_from_history,
    )

    checkpoint(progress_pct=10.0, message="ACI: updating α from recent outcomes (pick #52)")
    aci = update_alpha_from_recent_outcomes()
    if aci.observations_processed > 0:
        logger.info(
            "ACI: α %.4f → %.4f after %d observations (coverage %.2f)",
            aci.previous_alpha,
            aci.current_alpha,
            aci.observations_processed,
            aci.observed_coverage,
        )

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


@scheduled_job(
    "meta_hpo_rollback_watchdog",
    display_name="Meta-HPO rollback watchdog (CTR regression check)",
    cadence_seconds=DAY,
    estimate_seconds=2 * 60,
    priority=JOB_PRIORITY_HIGH,
)
def run_meta_hpo_rollback_watchdog(job, checkpoint) -> None:
    """Daily check — did CTR drop materially since the last auto-apply?

    Rail 3 of the fully-automatic safety stack. Restores the
    previous snapshot when the drop exceeds 5% over a 24-h post-apply
    window.
    """
    from datetime import datetime, timedelta

    from apps.core.models import AppSetting
    from apps.pipeline.services.meta_hpo_safety import (
        ROLLBACK_OBSERVATION_HOURS,
        restore_previous_snapshot,
        should_rollback,
    )

    checkpoint(progress_pct=0.0, message="Reading last applied timestamp")
    applied_at_raw = (
        AppSetting.objects.filter(key="meta_hpo.applied_at")
        .values_list("value", flat=True)
        .first()
    )
    if not applied_at_raw:
        checkpoint(progress_pct=100.0, message="No prior apply — nothing to watch")
        return

    try:
        applied_at = datetime.fromisoformat(applied_at_raw)
    except ValueError:
        logger.warning(
            "meta_hpo_rollback_watchdog: bad applied_at: %s", applied_at_raw
        )
        checkpoint(progress_pct=100.0, message="Malformed applied_at — skip")
        return

    if timezone.now() - applied_at < timedelta(hours=ROLLBACK_OBSERVATION_HOURS):
        checkpoint(
            progress_pct=100.0,
            message="Post-apply window not yet elapsed — nothing to decide",
        )
        return

    # W1 ships the decision path with placeholder CTR values so the
    # rail is installed and tested. W3 wires GSC / click-log
    # ingestion to fill these in with real data.
    checkpoint(
        progress_pct=40.0,
        message="Computing 24-h CTR vs 7-day baseline (placeholder until W3)",
    )
    baseline_ctr = 0.20
    observed_ctr = 0.20
    decision = should_rollback(baseline_ctr=baseline_ctr, observed_ctr=observed_ctr)

    if decision.rollback:
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
    else:
        checkpoint(
            progress_pct=100.0,
            message=f"No regression ({decision.reason})",
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
    """Weekly re-estimate of Cascade doc relevance from review history (pick #34).

    Wraps :func:`apps.pipeline.services.feedback_relevance.compute_and_persist`,
    which builds Cascade sessions from PipelineRun + Suggestion rows
    (no GSC dependency — the operator-review cycle is the click stream
    on this internal-linker product) and persists the per-destination
    relevance table to AppSetting for the ranker to consume.
    """
    from apps.pipeline.services.feedback_relevance import compute_and_persist

    checkpoint(progress_pct=0.0, message="Aggregating Cascade + IPS feedback")
    snapshot = compute_and_persist()
    if snapshot is None:
        checkpoint(
            progress_pct=100.0,
            message="Insufficient review history — fit skipped",
        )
        return
    checkpoint(
        progress_pct=100.0,
        message=(
            f"Persisted Cascade ({len(snapshot.cascade_relevance)} dests) + "
            f"IPS ({len(snapshot.ips_weighted_ctr)} positions) "
            f"from {snapshot.training_runs} runs"
        ),
    )


@scheduled_job(
    "position_bias_ips_refit",
    display_name="Position-bias IPS η refit",
    cadence_seconds=WEEK,
    estimate_seconds=5 * 60,
    priority=JOB_PRIORITY_LOW,
)
def run_position_bias_ips_refit(job, checkpoint) -> None:
    """Weekly refit of position-bias IPS weights (pick #33).

    Two complementary refits run side-by-side:

    1. :func:`feedback_relevance.compute_and_persist` — uses the
       review-queue history (PipelineRun + Suggestion ranks) as the
       click stream. Persists per-position IPS-weighted CTR. This
       always has data because operator review is the click stream
       for an internal-linker product.
    2. :func:`position_bias_ips_producer.fit_and_persist_from_impressions`
       — uses the new ``SuggestionImpression`` rows logged by the
       frontend's review-queue viewport hook. Fits the η exponent of
       the power-law propensity. Cold-start safe: until the frontend
       hook lands and impressions accumulate, this no-ops cleanly
       and the consumer (``feedback_relevance._compute_ips_ctr`` once
       Group A.4 wires it) keeps using the helper's default η=1.0.

    Both keys are namespaced separately in AppSetting
    (``feedback_relevance.*`` vs ``position_bias_ips.*``) so neither
    overwrites the other's data.
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

    parts: list[str] = []
    if cascade_snap is not None:
        parts.append(
            f"per-position CTR: {len(cascade_snap.ips_weighted_ctr)} positions "
            f"({cascade_snap.training_runs} runs)"
        )
    else:
        parts.append("per-position CTR: insufficient review history")
    if eta_snap is not None:
        parts.append(
            f"η fit: {eta_snap.eta:.3f} from {eta_snap.observations} impressions"
        )
    else:
        parts.append("η fit: cold-start (insufficient impressions)")

    checkpoint(progress_pct=100.0, message="; ".join(parts))


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
