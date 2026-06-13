"""Seasonality-aware traffic-spike detection (Prophet).

Why this module exists:
  The old spike rule compared a page's latest daily clicks against a flat
  7-day trailing average and alerted at 4x. That flags every ordinary
  weekly rhythm — a page that is reliably busy each Friday looks "spiky"
  every Friday — and misses a genuine surge on a normally-quiet day.

  Prophet (Taylor & Letham 2018) fits each page's own weekly seasonality
  and trend over a 90-day history, then forecasts the target day with an
  uncertainty band. A page is spiking only when its actual clicks exceed
  the forecast's upper bound by a margin — so the regular Friday peak is
  expected (no alert) and a surprise Tuesday surge is caught.

Cost control:
  Fitting Prophet per page is the expensive step, so it runs only on
  candidates that already look unusual: latest clicks above the noise
  floor AND above the page's own trailing mean. Candidates are capped
  (``max_items``) and fitted sequentially; pages with too few active days
  are skipped (not enough signal to model).

Reference: Taylor SJ, Letham B (2018), "Forecasting at scale",
The American Statistician 72(1) — doi:10.7287/peerj.preprints.3190v2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Quiet cmdstanpy's per-fit INFO chatter; we fit hundreds of small models.
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


@dataclass(frozen=True)
class SpikeFinding:
    """One page whose latest clicks exceeded its forecast upper bound."""

    item_id: int
    latest_clicks: int
    expected_upper: float


def _load_history(target_date: date, history_days: int) -> dict[int, dict[date, int]]:
    """Per-item {date: clicks} for GSC over the history window (ADBC pull)."""
    from apps.analytics.services.adbc_reader import read_sql_polars

    from apps.analytics.models import SearchMetric

    start = target_date - timedelta(days=history_days)
    table = SearchMetric._meta.db_table
    df = read_sql_polars(
        f'SELECT content_item_id, date, clicks FROM "{table}" '  # nosec B608 — table from model meta
        f"WHERE source = $1 AND date BETWEEN $2 AND $3",
        ["gsc", start, target_date],
    )
    history: dict[int, dict[date, int]] = {}
    for item_id, day, clicks in zip(
        df["content_item_id"].to_list(),
        df["date"].to_list(),
        df["clicks"].to_list(),
    ):
        history.setdefault(int(item_id), {})[day] = int(clicks or 0)
    return history


def _prescreen(
    history: dict[int, dict[date, int]],
    target_date: date,
    noise_floor: int,
    max_items: int,
) -> list[int]:
    """Cheap filter before the expensive fits: latest above floor AND above
    the page's own trailing mean. Returns item ids, busiest first, capped."""
    candidates: list[tuple[int, int]] = []
    for item_id, series in history.items():
        latest = series.get(target_date, 0)
        if latest <= noise_floor:
            continue
        prior = [c for d, c in series.items() if d != target_date]
        trailing_mean = sum(prior) / len(prior) if prior else 0.0
        if latest > trailing_mean:
            candidates.append((item_id, latest))
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return [item_id for item_id, _ in candidates[:max_items]]


def _forecast_upper(
    series: dict[date, int],
    target_date: date,
    history_days: int,
    min_active_days: int,
    interval_width: float,
) -> float | None:
    """Prophet upper-bound forecast for ``target_date``; None if too sparse."""
    import pandas as pd
    from prophet import Prophet

    start = target_date - timedelta(days=history_days)
    days = [start + timedelta(days=n) for n in range((target_date - start).days)]
    rows = [{"ds": d, "y": series.get(d, 0)} for d in days]  # exclude target day
    active = sum(1 for r in rows if r["y"] > 0)
    if active < min_active_days:
        return None
    model = Prophet(
        weekly_seasonality=True,
        daily_seasonality=False,
        yearly_seasonality=False,
        interval_width=interval_width,
    )
    model.fit(pd.DataFrame(rows))
    future = pd.DataFrame({"ds": [target_date]})
    forecast = model.predict(future)
    return float(forecast.iloc[-1]["yhat_upper"])


def detect_spikes(
    target_date: date,
    *,
    history_days: int,
    noise_floor: int,
    upper_bound_factor: float,
    max_items: int,
    min_active_days: int,
    interval_width: float = 0.95,
) -> list[SpikeFinding]:
    """Pages whose ``target_date`` clicks exceed their forecast upper bound."""
    history = _load_history(target_date, history_days)
    if not history:
        return []
    findings: list[SpikeFinding] = []
    for item_id in _prescreen(history, target_date, noise_floor, max_items):
        series = history[item_id]
        latest = series.get(target_date, 0)
        upper = _forecast_upper(
            series, target_date, history_days, min_active_days, interval_width
        )
        if upper is None:
            continue
        threshold = max(upper, float(noise_floor)) * upper_bound_factor
        if latest > threshold:
            findings.append(SpikeFinding(item_id, latest, round(upper, 2)))
    return findings


__all__ = ["SpikeFinding", "detect_spikes"]
