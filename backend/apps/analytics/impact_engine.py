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


class BayesianTrendAttributor:
    """FR-017: Poisson-Gamma Bayesian Attribution for GSC Clicks.

    Models the click-through rate (CTR) of a target page against the matched control
    trend to compute the probability of uplift.
    """

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
        """Calculate uplift probability and rewards vs matched control trend."""
        # 1. Compute Control Trend (Control Factor)
        # Using laplace smoothing to avoid division by zero
        control_ctr_base = (1 + control_clicks_base) / (1 + control_imps_base)
        control_ctr_post = (1 + control_clicks_post) / (1 + control_imps_post)
        trend = control_ctr_post / control_ctr_base if control_ctr_base > 0 else 1.0

        # 2. Bayesian Posterior Simulation (Monte Carlo)
        # Target Prior: Gamma(1, 1). Posterior: Gamma(1+k, 1+I)
        samples = 10000
        # scipy.stats.gamma uses (a, scale=1/b) for the (alpha, beta) parameterization
        dist_base = gamma(1 + target_clicks_base, scale=1 / (1 + target_imps_base))
        dist_post = gamma(1 + target_clicks_post, scale=1 / (1 + target_imps_post))

        # Vectorized sampling
        base_samples = dist_base.rvs(size=samples)
        post_samples = dist_post.rvs(size=samples)

        # Probability that post-CTR > (base-CTR * site-trend)
        prob_uplift = float(np.mean(post_samples > (base_samples * trend)))

        # 4. Labeling Logic
        lift_pct = 0.0
        if target_clicks_base > 0:
            # Expected lift normalized by trend
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
    """Build a candidate control pool: same content_type + silo, no applied suggestions."""
    pool_qs = (
        ContentItem.objects.filter(
            scope__silo_group=dest.scope.silo_group_id,
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

    target_agg = SearchMetric.objects.filter(
        content_item=dest,
        source="gsc",
        date__range=[baseline_start, baseline_end],
    ).aggregate(
        clicks=Sum("clicks"),
        impressions=Sum("impressions"),
        ctr=Avg("ctr"),
        average_position=Avg("average_position"),
    )
    t_clicks = float(target_agg["clicks"] or 0)
    t_imps = float(target_agg["impressions"] or 0)
    t_ctr = float(target_agg["ctr"] or 0)
    t_pos = float(target_agg["average_position"] or 0)

    candidate_aggs = (
        SearchMetric.objects.filter(
            content_item_id__in=pool_ids,
            source="gsc",
            date__range=[baseline_start, baseline_end],
        )
        .values("content_item_id")
        .annotate(
            clicks=Sum("clicks"),
            impressions=Sum("impressions"),
            ctr=Avg("ctr"),
            average_position=Avg("average_position"),
        )
    )
    cand_map = {int(r["content_item_id"]): r for r in candidate_aggs}

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


def compute_search_impact(
    suggestion: Suggestion, window_days: int = 28
) -> list[ImpactReport]:
    """
    Compute before/after impact for an applied suggestion.
    Uses a baseline window before applied_at and a post window after applied_at.

    Includes Keyword-level attribution (anchor text match) and
    Control-group normalization (market trend correction).
    """
    if not suggestion.applied_at:
        logger.info(
            f"Suggestion {suggestion.suggestion_id} is not applied; skipping impact."
        )
        return []

    # 1. Define Windows
    # Search Console has ~48-72 hour lag.
    latest_metric = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
    if not latest_metric:
        logger.info("No GSC data found in DB; cannot compute impact.")
        return []

    max_data_date = latest_metric.date
    post_start = suggestion.applied_at.date()

    # We need at least a few days of data to show anything
    if max_data_date < post_start + timedelta(days=3):
        logger.info(
            "Not enough post-apply data yet for %s.",
            suggestion.suggestion_id,
        )
        return []

    # Actual post window we can measure
    actual_post_end = min(post_start + timedelta(days=window_days - 1), max_data_date)
    actual_days = (actual_post_end - post_start).days + 1

    # Baseline window must be same size as post window
    baseline_end = post_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=actual_days - 1)

    # 2. Matched Control Group Normalization
    # Select similar items matched on pre-period metrics (Abadie et al. 2010)
    control_item_ids, match_quality, pool_size = _select_matched_controls(
        suggestion, baseline_start, baseline_end
    )
    is_conclusive = len(control_item_ids) >= _MIN_CONTROLS

    # Batch-fetch target item metrics in 2 queries
    target_baseline_qs = SearchMetric.objects.filter(
        content_item=suggestion.destination,
        source="gsc",
        date__range=[baseline_start, baseline_end],
    )
    target_post_qs = SearchMetric.objects.filter(
        content_item=suggestion.destination,
        source="gsc",
        date__range=[post_start, actual_post_end],
    )
    target_baseline_agg = target_baseline_qs.aggregate(
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        ctr=Avg("ctr"),
        average_position=Avg("average_position"),
    )
    target_post_agg = target_post_qs.aggregate(
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        ctr=Avg("ctr"),
        average_position=Avg("average_position"),
    )

    # Batch-fetch control group metrics
    control_baseline_agg: dict = {}
    control_post_agg: dict = {}
    if control_item_ids:
        control_baseline_agg = SearchMetric.objects.filter(
            content_item_id__in=control_item_ids,
            source="gsc",
            date__range=[baseline_start, baseline_end],
        ).aggregate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            ctr=Avg("ctr"),
            average_position=Avg("average_position"),
        )
        control_post_agg = SearchMetric.objects.filter(
            content_item_id__in=control_item_ids,
            source="gsc",
            date__range=[post_start, actual_post_end],
        ).aggregate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            ctr=Avg("ctr"),
            average_position=Avg("average_position"),
        )

    if not is_conclusive:
        GSCImpactSnapshot.objects.filter(
            suggestion=suggestion,
            window_type=f"{window_days}d",
        ).delete()

    if is_conclusive:
        try:
            # Native Python implementation of the Poisson-Gamma model
            attributor = BayesianTrendAttributor()

            # Get target aggregates for the attributor
            t_c_base = int(target_baseline_agg.get("clicks") or 0)
            t_i_base = int(target_baseline_agg.get("impressions") or 0)
            t_c_post = int(target_post_agg.get("clicks") or 0)
            t_i_post = int(target_post_agg.get("impressions") or 0)

            # Get control aggregates
            c_c_base = int(control_baseline_agg.get("clicks") or 0) if control_baseline_agg else 0
            c_i_base = int(control_baseline_agg.get("impressions") or 0) if control_baseline_agg else 0
            c_c_post = int(control_post_agg.get("clicks") or 0) if control_post_agg else 0
            c_i_post = int(control_post_agg.get("impressions") or 0) if control_post_agg else 0

            result = attributor.compute_uplift(
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
                    window_type=f"{window_days}d",
                    defaults={
                        "apply_date": suggestion.applied_at,
                        "baseline_clicks": t_c_base,
                        "post_clicks": t_c_post,
                        "baseline_impressions": t_i_base,
                        "post_impressions": t_i_post,
                        "lift_clicks_pct": result.get("lift_clicks_pct", 0.0),
                        "lift_clicks_absolute": t_c_post - t_c_base,
                        "probability_of_uplift": result.get(
                            "probability_of_uplift", 0.0
                        ),
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
                "Failed to run native Bayesian attribution for %s: %s",
                suggestion.suggestion_id,
                exc,
            )

    # 3. Matched Control Group Normalization (already computed above)
    metrics_to_calc = ["impressions", "clicks", "ctr", "average_position"]
    click_control_multiplier = 1.0
    reports = []

    for metric in metrics_to_calc:
        # A. Target Item Performance
        target_base = float(target_baseline_agg.get(metric) or 0)
        target_post_val = float(target_post_agg.get(metric) or 0)

        # B. Control Group Trend
        control_base = (
            float(control_baseline_agg.get(metric) or 0)
            if control_baseline_agg
            else 0.0
        )
        control_post = (
            float(control_post_agg.get(metric) or 0) if control_post_agg else 0.0
        )

        control_lift_multiplier = 1.0
        if control_base > 0:
            control_lift_multiplier = control_post / control_base
        if metric == "clicks":
            click_control_multiplier = control_lift_multiplier

        # C. Normalized Lift
        normalized_before = target_base * control_lift_multiplier

        delta = 0.0
        if is_conclusive and normalized_before > 0:
            delta = ((target_post_val - normalized_before) / normalized_before) * 100
        elif is_conclusive and target_post_val > 0:
            delta = 100.0
        # When inconclusive, delta stays 0.0 — we don't trust the result

        report, _ = ImpactReport.objects.update_or_create(
            suggestion=suggestion,
            metric_type=metric,
            defaults={
                "before_value": target_base,
                "after_value": target_post_val,
                "delta_percent": delta,
                "before_date_range": {
                    "start": baseline_start.isoformat(),
                    "end": baseline_end.isoformat(),
                },
                "after_date_range": {
                    "start": post_start.isoformat(),
                    "end": actual_post_end.isoformat(),
                },
                "control_pool_size": pool_size,
                "control_match_count": len(control_item_ids),
                "control_match_quality": match_quality,
                "is_conclusive": is_conclusive,
            },
        )
        reports.append(report)

    # 3. Keyword-Level Impact Attribution
    _compute_keyword_impacts(
        suggestion,
        baseline_start,
        baseline_end,
        post_start,
        actual_post_end,
        click_control_multiplier,
    )

    return reports


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

    # Get all queries for this item in the total window
    queries = (
        SearchMetric.objects.filter(
            content_item=suggestion.destination,
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

        b_stats = SearchMetric.objects.filter(
            content_item=suggestion.destination,
            source="gsc",
            query=q_text,
            date__range=[b_start, b_end],
        ).aggregate(
            clks=Sum("clicks"), imps=Sum("impressions"), pos=Avg("average_position")
        )

        p_stats = SearchMetric.objects.filter(
            content_item=suggestion.destination,
            source="gsc",
            query=q_text,
            date__range=[p_start, p_end],
        ).aggregate(
            clks=Sum("clicks"), imps=Sum("impressions"), pos=Avg("average_position")
        )

        c_base = b_stats["clks"] or 0
        c_post = p_stats["clks"] or 0

        # Normalize baseline against control trend
        normalized_c_base = float(c_base) * control_multiplier
        lift = 0.0
        if normalized_c_base > 0:
            lift = ((float(c_post) - normalized_c_base) / normalized_c_base) * 100
        elif c_post > 0:
            lift = 100.0

        is_match = anchor in q_text.lower()

        GSCKeywordImpact.objects.update_or_create(
            suggestion=suggestion,
            query=q_text,
            defaults={
                "clicks_baseline": c_base,
                "clicks_post": c_post,
                "impressions_baseline": b_stats["imps"] or 0,
                "impressions_post": p_stats["imps"] or 0,
                "position_baseline": b_stats["pos"],
                "position_post": p_stats["pos"],
                "lift_percent": lift,
                "is_anchor_match": is_match,
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
