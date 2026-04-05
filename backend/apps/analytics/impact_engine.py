"""Impact Attribution Engine for FR-017 GSC Search Outcome Attribution."""

from __future__ import annotations

import logging
from datetime import timedelta, date
from typing import Any

from django.db.models import Avg, Sum, Q
from django.utils import timezone

from apps.suggestions.models import Suggestion
from apps.content.models import ContentItem
from .models import SearchMetric, ImpactReport

logger = logging.getLogger(__name__)


def compute_search_impact(suggestion: Suggestion, window_days: int = 28) -> list[ImpactReport]:
    """
    Compute before/after impact for an applied suggestion.
    Uses a baseline window before applied_at and a post window after applied_at.
    
    Includes Keyword-level attribution (anchor text match) and 
    Control-group normalization (market trend correction).
    """
    if not suggestion.applied_at:
        logger.info(f"Suggestion {suggestion.suggestion_id} is not applied; skipping impact.")
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
        logger.info(f"Not enough post-apply data yet for {suggestion.suggestion_id}.")
        return []

    # Actual post window we can measure
    actual_post_end = min(post_start + timedelta(days=window_days - 1), max_data_date)
    actual_days = (actual_post_end - post_start).days + 1
    
    # Baseline window must be same size as post window
    baseline_end = post_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=actual_days - 1)

    # 2. Trigger Bayesian Attribution (C# Worker / Slice 4)
    from apps.graph.services.http_worker_client import run_job
    from .views import get_gsc_settings
    from .models import GSCImpactSnapshot
    
    gsc_settings = get_gsc_settings()
    property_url = gsc_settings.get("property_url")
    
    if property_url:
        payload = {
            "SuggestionId": str(suggestion.suggestion_id),
            "PageUrl": suggestion.destination.url,
            "PropertyUrl": property_url,
            "ApplyDate": suggestion.applied_at.isoformat(),
            "WindowDays": actual_days
        }
        try:
            # Synchronous call to the refined C# worker
            result = run_job("gsc_attribution", payload)
            
            if result and result.get("RewardLabel") != "inconclusive":
                # Fetch impressions locally since C# only returns clicks
                baseline_imps = _get_aggregated_metric(suggestion.destination, "impressions", baseline_start, baseline_end)
                post_imps = _get_aggregated_metric(suggestion.destination, "impressions", post_start, actual_post_end)

                GSCImpactSnapshot.objects.update_or_create(
                    suggestion=suggestion,
                    window_type=f"{window_days}d",
                    defaults={
                        "apply_date": suggestion.applied_at,
                        "baseline_clicks": result.get("BaselineClicks", 0),
                        "post_clicks": result.get("PostClicks", 0),
                        "baseline_impressions": int(baseline_imps),
                        "post_impressions": int(post_imps),
                        "lift_clicks_pct": result.get("LiftClicksPct", 0.0),
                        "lift_clicks_absolute": result.get("PostClicks", 0) - result.get("BaselineClicks", 0),
                        "probability_of_uplift": result.get("ProbabilityOfUplift", 0.0),
                        "reward_label": result.get("RewardLabel", "inconclusive"),
                    }
                )
                logger.info(f"Bayesian attribution complete for {suggestion.suggestion_id}: {result.get('RewardLabel')}")
        except Exception as exc:
            logger.error(f"Failed to run C# Bayesian attribution for {suggestion.suggestion_id}: {exc}")

    # 3. Control Group Normalization (Legacy Python reporting)
    # Find similar items (same silo) that had NO links applied in the same whole window
    control_items = ContentItem.objects.filter(
        scope__silo_group=suggestion.destination.scope.silo_group_id
    ).exclude(
        pk=suggestion.destination_id
    ).exclude(
        destination_suggestions__status="applied",
        destination_suggestions__applied_at__range=[baseline_start, actual_post_end]
    )[:10] # Small sample is enough for trend

    metrics_to_calc = ["impressions", "clicks", "ctr", "average_position"]
    click_control_multiplier = 1.0
    reports = []

    for metric in metrics_to_calc:
        # A. Target Item Performance
        target_base = _get_aggregated_metric(suggestion.destination, metric, baseline_start, baseline_end)
        target_post = _get_aggregated_metric(suggestion.destination, metric, post_start, actual_post_end)
        
        # B. Control Group Trend (Market Normalization)
        # We calculate the aggregate lift of the control group to see if the whole site grew
        control_base = 0.0
        control_post = 0.0
        for c_item in control_items:
            control_base += _get_aggregated_metric(c_item, metric, baseline_start, baseline_end)
            control_post += _get_aggregated_metric(c_item, metric, post_start, actual_post_end)
        
        control_lift_multiplier = 1.0
        if control_base > 0:
            control_lift_multiplier = control_post / control_base
        if metric == "clicks":
            click_control_multiplier = control_lift_multiplier
            
        # C. Normalized Lift calculation:
        # If site grew 10% (multiplier 1.1) and target grew 20%, target net lift is ~9%
        normalized_before = target_base * control_lift_multiplier
        
        delta = 0.0
        if normalized_before > 0:
            delta = ((target_post - normalized_before) / normalized_before) * 100
        elif target_post > 0:
            delta = 100.0

        report, _ = ImpactReport.objects.update_or_create(
            suggestion=suggestion,
            metric_type=metric,
            defaults={
                "before_value": target_base,
                "after_value": target_post,
                "delta_percent": delta,
                "before_date_range": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
                "after_date_range": {"start": post_start.isoformat(), "end": actual_post_end.isoformat()},
            }
        )
        reports.append(report)

    # 3. Keyword-Level Impact Attribution
    _compute_keyword_impacts(
        suggestion, 
        baseline_start, baseline_end, 
        post_start, actual_post_end, 
        click_control_multiplier
    )

    return reports


def _compute_keyword_impacts(
    suggestion: Suggestion, 
    b_start: date, b_end: date, 
    p_start: date, p_end: date,
    control_multiplier: float
) -> None:
    """Calculate and store per-query lift for the suggestion's destination."""
    from .models import GSCKeywordImpact
    
    # Get all queries for this item in the total window
    queries = SearchMetric.objects.filter(
        content_item=suggestion.destination,
        source="gsc",
        date__range=[b_start, p_end]
    ).exclude(query="").values_list("query", flat=True).distinct()
    
    anchor = (suggestion.anchor_edited or suggestion.anchor_phrase or "").lower().strip()
    
    for q_text in queries:
        if not q_text:
            continue
            
        b_stats = SearchMetric.objects.filter(
            content_item=suggestion.destination,
            source="gsc",
            query=q_text,
            date__range=[b_start, b_end]
        ).aggregate(
            clks=Sum("clicks"), 
            imps=Sum("impressions"), 
            pos=Avg("average_position")
        )
        
        p_stats = SearchMetric.objects.filter(
            content_item=suggestion.destination,
            source="gsc",
            query=q_text,
            date__range=[p_start, p_end]
        ).aggregate(
            clks=Sum("clicks"), 
            imps=Sum("impressions"), 
            pos=Avg("average_position")
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
            }
        )


def _get_aggregated_metric(item: ContentItem, metric: str, start: date, end: date) -> float:
    """Helper to sum or average metrics for a window."""
    qs = SearchMetric.objects.filter(
        content_item=item,
        source="gsc",
        date__range=[start, end]
    )
    
    # We aggregate across all queries for this page
    if metric in ["impressions", "clicks"]:
        return qs.aggregate(val=Sum(metric))["val"] or 0.0
    else:
        return qs.aggregate(val=Avg(metric))["val"] or 0.0
