"""Impact Attribution Engine for FR-017 GSC Search Outcome Attribution.

Control-group matching follows the causal-inference approach from:
  Abadie, Diamond & Hainmueller (2010) "Synthetic Control Methods"
  Brodersen et al. (2015) "Inferring causal impact using Bayesian
  structural time-series models"
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta, date

from django.db.models import Avg, Sum
from scipy.stats import gamma
import numpy as np

from apps.suggestions.models import Suggestion
from apps.content.models import ContentItem
from .models import SearchMetric, ImpactReport, GSCImpactSnapshot

logger = logging.getLogger(__name__)

# Minimum valid controls for a conclusive result
_MIN_CONTROLS = 3
# Maximum candidates to consider in the initial pool
_POOL_MAX = 100
# Default number of matched controls to select
_CONTROL_K = 5
# Standard 4-field GSC aggregate reused across all window queries
_SEARCH_METRIC_AGGREGATE = {
    "impressions": Sum("impressions"),
    "clicks": Sum("clicks"),
    "ctr": Avg("ctr"),
    "average_position": Avg("average_position"),
}
# Metrics tracked in ImpactReport — one row per metric per suggestion
_TRACKED_METRICS = ["impressions", "clicks", "ctr", "average_position"]


def _gsc_aggregate(qs) -> dict:
    """Run the standard 4-field GSC aggregate on a pre-filtered queryset."""
    return qs.filter(source="gsc").aggregate(**_SEARCH_METRIC_AGGREGATE)


class BayesianTrendAttributor:
    """FR-017: Poisson-Gamma Bayesian Attribution for GSC Clicks.

    Models the click-through rate (CTR) of a target page against the matched control
    trend to compute the probability of uplift.
    """

    def _compute_control_trend(
        self,
        c_clks_base: int,
        c_imps_base: int,
        c_clks_post: int,
        c_imps_post: int,
    ) -> float:
        """Return the site-wide CTR trend factor using Laplace-smoothed rates."""
        ctr_base = (1 + c_clks_base) / (1 + c_imps_base)
        ctr_post = (1 + c_clks_post) / (1 + c_imps_post)
        return ctr_post / ctr_base if ctr_base > 0 else 1.0

    def _run_monte_carlo(
        self,
        t_clks_base: int,
        t_imps_base: int,
        t_clks_post: int,
        t_imps_post: int,
        trend: float,
        samples: int = 10_000,
    ) -> float:
        """Return P(post_CTR > base_CTR * trend) via Poisson-Gamma Monte Carlo.

        scipy.stats.gamma uses (a, scale=1/b) for the (alpha, beta) parameterization.
        Prior: Gamma(1, 1). Posterior: Gamma(1+k, 1+I).
        """
        dist_base = gamma(1 + t_clks_base, scale=1 / (1 + t_imps_base))
        dist_post = gamma(1 + t_clks_post, scale=1 / (1 + t_imps_post))
        return float(
            np.mean(dist_post.rvs(size=samples) > dist_base.rvs(size=samples) * trend)
        )

    def compute_uplift(
        self,
        target_clicks_base: int,
        target_imps_base: int,
        target_clicks_post: int,
        target_imps_post: int,
        control_clicks_base: int,
        control_imps_base: int,
        control_clicks_post: int,
        control_imps_post: int,
    ) -> dict:
        """Calculate uplift probability and reward label vs matched control trend."""
        trend = self._compute_control_trend(
            control_clicks_base,
            control_imps_base,
            control_clicks_post,
            control_imps_post,
        )
        prob_uplift = self._run_monte_carlo(
            target_clicks_base,
            target_imps_base,
            target_clicks_post,
            target_imps_post,
            trend,
        )

        lift_pct = 0.0
        if target_clicks_base > 0:
            expected_base = target_clicks_base * trend
            lift_pct = ((target_clicks_post - expected_base) / expected_base) * 100

        reward = "neutral"
        if prob_uplift > 0.90:
            reward = "positive"
        elif prob_uplift < 0.10:
            reward = "negative"
        elif target_clicks_base + target_clicks_post < 5:
            reward = "inconclusive"

        return {
            "probability_of_uplift": round(prob_uplift, 4),
            "lift_clicks_pct": round(lift_pct, 2),
            "reward_label": reward,
            "site_trend": round(trend, 4),
        }


def _build_control_pool(
    dest: ContentItem,
    baseline_start: date,
    baseline_end: date,
    pool_max: int = _POOL_MAX,
) -> list[int]:
    """Build a candidate control pool: same content_type + silo, no applied suggestions.

    Returns an empty list when the destination has no scope, or its
    scope has no silo group assigned. Both are nullable in the schema
    (``ContentItem.scope.null=True``, ``ScopeItem.silo_group.null=True``).
    Without this guard the original code raised ``AttributeError`` on
    scope-less items and silently matched unrelated items via
    ``scope__silo_group=None`` when the silo was unassigned. Either
    failure mode would corrupt attribution.
    """
    scope = getattr(dest, "scope", None)
    silo_group_id = getattr(scope, "silo_group_id", None) if scope is not None else None
    if scope is None or silo_group_id is None:
        logger.info(
            "_build_control_pool: destination=%s has no scope/silo — "
            "returning empty pool (attribution will be inconclusive).",
            getattr(dest, "pk", None),
        )
        return []

    pool_qs = (
        ContentItem.objects.filter(
            scope__silo_group_id=silo_group_id,
            content_type=dest.content_type,
        )
        .exclude(pk=dest.pk)
        .exclude(
            destination_suggestions__status="applied",
            destination_suggestions__applied_at__range=[
                baseline_start,
                baseline_end + timedelta(days=60),
            ],
        )
        .values_list("pk", flat=True)[:pool_max]
    )
    return list(pool_qs)


def _score_candidate_distance(
    cand: dict,
    target_clicks: float,
    target_imps: float,
    target_ctr: float,
    target_pos: float,
) -> float:
    """Normalized Euclidean distance between a candidate and the target."""
    c_clicks = float(cand["clicks"] or 0)
    c_imps = float(cand["impressions"] or 0)
    c_ctr = float(cand["ctr"] or 0)
    c_pos = float(cand["average_position"] or 0)

    dist_sq = ((target_clicks - c_clicks) / max(target_clicks, 1.0)) ** 2
    dist_sq += ((target_imps - c_imps) / max(target_imps, 1.0)) ** 2
    dist_sq += (target_ctr - c_ctr) ** 2
    dist_sq += ((target_pos - c_pos) / max(target_pos, 1.0)) ** 2
    return math.sqrt(dist_sq)


def _aggregate_control_candidates(
    pool_ids: list[int],
    baseline_start: date,
    baseline_end: date,
) -> dict[int, dict]:
    """Return per-item GSC aggregates keyed by content_item_id for all pool candidates."""
    rows = (
        SearchMetric.objects.filter(
            content_item_id__in=pool_ids,
            source="gsc",
            date__range=[baseline_start, baseline_end],
        )
        .values("content_item_id")
        .annotate(**_SEARCH_METRIC_AGGREGATE)
    )
    return {int(r["content_item_id"]): r for r in rows}


def _select_matched_controls(
    suggestion: Suggestion,
    baseline_start: date,
    baseline_end: date,
    k: int = _CONTROL_K,
) -> tuple[list[int], float | None, int]:
    """Select k controls matched on pre-period GSC metrics.

    Returns (control_ids, avg_match_quality, pool_size).
    """
    dest = suggestion.destination
    pool_ids = _build_control_pool(dest, baseline_start, baseline_end)
    pool_size = len(pool_ids)

    if pool_size < _MIN_CONTROLS:
        return [], None, pool_size

    target_agg = _gsc_aggregate(
        SearchMetric.objects.filter(
            content_item=dest,
            date__range=[baseline_start, baseline_end],
        )
    )
    t_clicks = float(target_agg["clicks"] or 0)
    t_imps = float(target_agg["impressions"] or 0)
    t_ctr = float(target_agg["ctr"] or 0)
    t_pos = float(target_agg["average_position"] or 0)

    cand_map = _aggregate_control_candidates(pool_ids, baseline_start, baseline_end)
    scored = [
        (cid, _score_candidate_distance(cand_map[cid], t_clicks, t_imps, t_ctr, t_pos))
        for cid in pool_ids
        if cid in cand_map
    ]
    scored.sort(key=lambda x: x[1])
    selected = scored[:k]

    if len(selected) < _MIN_CONTROLS:
        return [], None, pool_size

    control_ids = [cid for cid, _ in selected]
    avg_dist = sum(d for _, d in selected) / len(selected)
    match_quality = max(0.0, min(1.0, 1.0 - avg_dist))
    return control_ids, round(match_quality, 4), pool_size


def _csi_compute_windows(suggestion: Suggestion, window_days: int) -> dict | None:
    """Validate data availability and compute the baseline/post date windows.

    Returns a 4-key date dict, or None when data is absent or too fresh to measure.
    """
    if not suggestion.applied_at:
        logger.info("Suggestion %s not applied; skipping.", suggestion.suggestion_id)
        return None
    latest = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
    if not latest:
        logger.info("No GSC data found in DB; cannot compute impact.")
        return None
    post_start = suggestion.applied_at.date()
    if latest.date < post_start + timedelta(days=3):
        logger.info("Not enough post-apply data yet for %s.", suggestion.suggestion_id)
        return None
    actual_post_end = min(post_start + timedelta(days=window_days - 1), latest.date)
    actual_days = (actual_post_end - post_start).days + 1
    baseline_end = post_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=actual_days - 1)
    return {
        "post_start": post_start,
        "actual_post_end": actual_post_end,
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
    }


def _csi_phase_a_match_candidates(
    suggestion: Suggestion, window_days: int
) -> dict | None:
    """Phase A: compute windows, select controls, batch-fetch all period metrics.

    Returns a context dict consumed by phases B and C, or None for early exit.
    """
    wins = _csi_compute_windows(suggestion, window_days)
    if wins is None:
        return None
    b_start, b_end = wins["baseline_start"], wins["baseline_end"]
    p_start, p_end = wins["post_start"], wins["actual_post_end"]

    control_ids, match_quality, pool_size = _select_matched_controls(
        suggestion, b_start, b_end
    )
    is_conclusive = len(control_ids) >= _MIN_CONTROLS
    dest = suggestion.destination

    t_base = _gsc_aggregate(
        SearchMetric.objects.filter(content_item=dest, date__range=[b_start, b_end])
    )
    t_post = _gsc_aggregate(
        SearchMetric.objects.filter(content_item=dest, date__range=[p_start, p_end])
    )
    c_base, c_post = {}, {}
    if control_ids:
        c_base = _gsc_aggregate(
            SearchMetric.objects.filter(
                content_item_id__in=control_ids, date__range=[b_start, b_end]
            )
        )
        c_post = _gsc_aggregate(
            SearchMetric.objects.filter(
                content_item_id__in=control_ids, date__range=[p_start, p_end]
            )
        )
    return {
        **wins,
        "control_ids": control_ids,
        "is_conclusive": is_conclusive,
        "match_quality": match_quality,
        "pool_size": pool_size,
        "t_base": t_base,
        "t_post": t_post,
        "c_base": c_base,
        "c_post": c_post,
        "window_days": window_days,
    }


def _impact_report_defaults(
    target_base: float,
    target_post: float,
    delta: float,
    ctx: dict,
) -> dict:
    """Build the defaults dict for ImpactReport.update_or_create from context."""
    return {
        "before_value": target_base,
        "after_value": target_post,
        "delta_percent": delta,
        "before_date_range": {
            "start": ctx["baseline_start"].isoformat(),
            "end": ctx["baseline_end"].isoformat(),
        },
        "after_date_range": {
            "start": ctx["post_start"].isoformat(),
            "end": ctx["actual_post_end"].isoformat(),
        },
        "control_pool_size": ctx["pool_size"],
        "control_match_count": len(ctx["control_ids"]),
        "control_match_quality": ctx["match_quality"],
        "is_conclusive": ctx["is_conclusive"],
    }


def _csi_phase_b_aggregate_impacts(
    suggestion: Suggestion, ctx: dict
) -> list[ImpactReport]:
    """Phase B: compute normalized lift for 4 GSC metrics; upsert ImpactReport rows."""
    is_conclusive = ctx["is_conclusive"]
    t_base, t_post = ctx["t_base"], ctx["t_post"]
    c_base, c_post = ctx["c_base"], ctx["c_post"]
    b_start, b_end = ctx["baseline_start"], ctx["baseline_end"]
    p_start, p_end = ctx["post_start"], ctx["actual_post_end"]

    click_ctrl_mult = 1.0
    reports = []
    for metric in _TRACKED_METRICS:
        tgt_base = float(t_base.get(metric) or 0)
        tgt_post = float(t_post.get(metric) or 0)
        ctrl_base = float(c_base.get(metric) or 0) if c_base else 0.0
        ctrl_post_v = float(c_post.get(metric) or 0) if c_post else 0.0
        ctrl_mult = (ctrl_post_v / ctrl_base) if ctrl_base > 0 else 1.0
        if metric == "clicks":
            click_ctrl_mult = ctrl_mult
        norm_before = tgt_base * ctrl_mult
        if is_conclusive and norm_before > 0:
            delta = ((tgt_post - norm_before) / norm_before) * 100
        elif is_conclusive and tgt_post > 0:
            delta = 100.0
        else:
            delta = 0.0
        report, _ = ImpactReport.objects.update_or_create(
            suggestion=suggestion,
            metric_type=metric,
            defaults=_impact_report_defaults(tgt_base, tgt_post, delta, ctx),
        )
        reports.append(report)
    _compute_keyword_impacts(
        suggestion, b_start, b_end, p_start, p_end, click_ctrl_mult
    )
    return reports


def _csi_phase_c_persist_snapshot(suggestion: Suggestion, ctx: dict) -> None:
    """Phase C: delete stale snapshot or persist Bayesian result to GSCImpactSnapshot."""
    window_type = f"{ctx['window_days']}d"
    if not ctx["is_conclusive"]:
        GSCImpactSnapshot.objects.filter(
            suggestion=suggestion, window_type=window_type
        ).delete()
        return
    t_base, t_post = ctx["t_base"], ctx["t_post"]
    c_base, c_post = ctx["c_base"], ctx["c_post"]
    t_c_base, t_i_base = (
        int(t_base.get("clicks") or 0),
        int(t_base.get("impressions") or 0),
    )
    t_c_post, t_i_post = (
        int(t_post.get("clicks") or 0),
        int(t_post.get("impressions") or 0),
    )
    c_c_base = int(c_base.get("clicks") or 0) if c_base else 0
    c_i_base = int(c_base.get("impressions") or 0) if c_base else 0
    c_c_post = int(c_post.get("clicks") or 0) if c_post else 0
    c_i_post = int(c_post.get("impressions") or 0) if c_post else 0
    try:
        result = BayesianTrendAttributor().compute_uplift(
            target_clicks_base=t_c_base,
            target_imps_base=t_i_base,
            target_clicks_post=t_c_post,
            target_imps_post=t_i_post,
            control_clicks_base=c_c_base,
            control_imps_base=c_i_base,
            control_clicks_post=c_c_post,
            control_imps_post=c_i_post,
        )
        if result and result.get("reward_label") != "inconclusive":
            GSCImpactSnapshot.objects.update_or_create(
                suggestion=suggestion,
                window_type=window_type,
                defaults={
                    "apply_date": suggestion.applied_at,
                    "baseline_clicks": t_c_base,
                    "post_clicks": t_c_post,
                    "baseline_impressions": t_i_base,
                    "post_impressions": t_i_post,
                    "lift_clicks_pct": result.get("lift_clicks_pct", 0.0),
                    "lift_clicks_absolute": t_c_post - t_c_base,
                    "probability_of_uplift": result.get("probability_of_uplift", 0.0),
                    "reward_label": result.get("reward_label", "inconclusive"),
                },
            )
            logger.info(
                "Bayesian attribution complete for %s: %s",
                suggestion.suggestion_id,
                result.get("reward_label"),
            )
    except Exception as exc:
        logger.error(
            "Bayesian attribution failed for %s: %s", suggestion.suggestion_id, exc
        )


def compute_search_impact(
    suggestion: Suggestion, window_days: int = 28
) -> list[ImpactReport]:
    """Compute before/after GSC impact for an applied suggestion.

    Uses causal-inference control matching (Abadie et al. 2010). Returns one
    ImpactReport per tracked metric; side-effects: upserts GSCImpactSnapshot
    and GSCKeywordImpact rows.
    """
    ctx = _csi_phase_a_match_candidates(suggestion, window_days)
    if ctx is None:
        return []
    _csi_phase_c_persist_snapshot(suggestion, ctx)
    return _csi_phase_b_aggregate_impacts(suggestion, ctx)


def _fetch_keyword_stats(
    destination: ContentItem, q_text: str, start: date, end: date
) -> dict:
    """Aggregate GSC clicks/impressions/position for one query in one time window."""
    return SearchMetric.objects.filter(
        content_item=destination,
        source="gsc",
        query=q_text,
        date__range=[start, end],
    ).aggregate(
        clks=Sum("clicks"),
        imps=Sum("impressions"),
        pos=Avg("average_position"),
    )


def _compute_query_lift(c_base: int, c_post: int, control_multiplier: float) -> float:
    """Return the normalized click lift for a single query vs the control trend."""
    normalized = float(c_base) * control_multiplier
    if normalized > 0:
        return ((float(c_post) - normalized) / normalized) * 100
    if c_post > 0:
        return 100.0
    return 0.0


def _compute_keyword_impacts(
    suggestion: Suggestion,
    b_start: date,
    b_end: date,
    p_start: date,
    p_end: date,
    control_multiplier: float,
) -> None:
    """Calculate and store per-query lift for the suggestion's destination."""
    from .models import GSCKeywordImpact

    dest = suggestion.destination
    queries = (
        SearchMetric.objects.filter(
            content_item=dest,
            source="gsc",
            date__range=[b_start, p_end],
        )
        .exclude(query="")
        .values_list("query", flat=True)
        .distinct()
    )
    anchor = (
        (suggestion.anchor_edited or suggestion.anchor_phrase or "").lower().strip()
    )

    for q_text in queries:
        if not q_text:
            continue
        b_stats = _fetch_keyword_stats(dest, q_text, b_start, b_end)
        p_stats = _fetch_keyword_stats(dest, q_text, p_start, p_end)
        lift = _compute_query_lift(
            b_stats["clks"] or 0, p_stats["clks"] or 0, control_multiplier
        )
        GSCKeywordImpact.objects.update_or_create(
            suggestion=suggestion,
            query=q_text,
            defaults={
                "clicks_baseline": b_stats["clks"] or 0,
                "clicks_post": p_stats["clks"] or 0,
                "impressions_baseline": b_stats["imps"] or 0,
                "impressions_post": p_stats["imps"] or 0,
                "position_baseline": b_stats["pos"],
                "position_post": p_stats["pos"],
                "lift_percent": lift,
                "is_anchor_match": anchor in q_text.lower(),
            },
        )


def _get_aggregated_metric(
    item: ContentItem, metric: str, start: date, end: date
) -> float:
    """Helper to sum or average metrics for a window."""
    qs = SearchMetric.objects.filter(
        content_item=item, source="gsc", date__range=[start, end]
    )

    # We aggregate across all queries for this page
    if metric in ["impressions", "clicks"]:
        return qs.aggregate(val=Sum(metric))["val"] or 0.0
    else:
        return qs.aggregate(val=Avg(metric))["val"] or 0.0
