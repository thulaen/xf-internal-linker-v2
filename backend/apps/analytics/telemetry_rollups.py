"""DataFusion-backed breakdown rollups for the telemetry dashboard.

Why this module exists:
  The analytics dashboard's device / channel / country breakdowns used
  to run three GROUP BY aggregations against Postgres on every page
  load, uncached. This module snapshots the telemetry window to a local
  Parquet file (refreshed at most every 15 minutes) and serves the
  breakdowns from one DataFusion SQL pass per dimension, so repeated
  dashboard loads stop re-aggregating on the transactional database.

Staleness contract: at most ``_SNAPSHOT_MAX_AGE_SECONDS`` behind the
live table — acceptable because the telemetry table itself is only fed
by hourly/daily sync jobs.

Reference: Apache DataFusion — https://datafusion.apache.org/
"""

from __future__ import annotations

import logging
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from .country_filters import BLOCKED_TELEMETRY_COUNTRY_VALUES

logger = logging.getLogger(__name__)

_SNAPSHOT_MAX_AGE_SECONDS = 15 * 60
_EXPORT_WINDOW_DAYS = 90  # matches the dashboard's maximum days filter
_BREAKDOWN_TOP_N = 6
_ALLOWED_DIMENSIONS = frozenset(
    ("device_category", "default_channel_group", "country")
)


def _snapshot_path() -> Path:
    return (
        Path(tempfile.gettempdir())
        / "xf-analytics-snapshots"
        / "telemetry_window.parquet"
    )


def _snapshot_is_fresh(path: Path) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < _SNAPSHOT_MAX_AGE_SECONDS
    except OSError:
        return False


def _refresh_snapshot(path: Path) -> bool:
    """Export the telemetry window to Parquet; False when the table is empty.

    A fixed filename is reused (atomic replace) so snapshots never pile
    up. An empty table deletes any stale file so old data cannot leak.
    """
    import polars as pl  # pylint: disable=import-error

    from apps.pipeline.services._parquet_io import write_parquet_atomic

    from .models import SuggestionTelemetryDaily

    start = timezone.now().date() - timedelta(days=_EXPORT_WINDOW_DAYS)
    rows = list(
        SuggestionTelemetryDaily.objects.filter(date__gte=start).values_list(
            "date",
            "telemetry_source",
            "device_category",
            "default_channel_group",
            "country",
            "impressions",
            "clicks",
            "engaged_sessions",
        )
    )
    if not rows:
        path.unlink(missing_ok=True)
        return False
    columns = list(zip(*rows))
    df = pl.DataFrame(
        {
            "date": list(columns[0]),
            "telemetry_source": list(columns[1]),
            "device_category": list(columns[2]),
            "default_channel_group": list(columns[3]),
            "country": list(columns[4]),
            "impressions": list(columns[5]),
            "clicks": list(columns[6]),
            "engaged_sessions": list(columns[7]),
        }
    )
    write_parquet_atomic(df, path)
    return True


def breakdown_rows(dimension: str, *, days: int, source: str | None) -> list[dict]:
    """Top-6 rollup of one dimension via a single DataFusion SQL pass.

    Matches the retired ORM aggregation exactly: rows inside the
    ``days`` window, blocked countries excluded (NULL country kept,
    mirroring Django's ``exclude(country__in=...)`` behaviour), optional
    telemetry-source filter, summed measures, ordered by clicks then
    impressions then label.
    """
    if dimension not in _ALLOWED_DIMENSIONS:
        raise ValueError(f"Unsupported breakdown dimension: {dimension}")

    path = _snapshot_path()
    if not _snapshot_is_fresh(path) and not _refresh_snapshot(path):
        return []

    from apps.pipeline.services.datafusion_engine import DataFusionEngine

    engine = DataFusionEngine()
    engine.register_parquet_file("telemetry", path)
    cutoff = timezone.now().date() - timedelta(days=int(days) - 1)
    blocked = ", ".join(f"'{value}'" for value in BLOCKED_TELEMETRY_COUNTRY_VALUES)
    source_clause = (
        f"AND telemetry_source = '{source}'" if source in ("ga4", "matomo") else ""
    )
    query = f'SELECT "{dimension}" AS label_value, SUM(impressions) AS impressions, SUM(clicks) AS clicks, SUM(engaged_sessions) AS engaged_sessions FROM telemetry WHERE "date" >= DATE \'{cutoff}\' AND (country IS NULL OR country NOT IN ({blocked})) {source_clause} GROUP BY "{dimension}" ORDER BY clicks DESC, impressions DESC, label_value ASC LIMIT {_BREAKDOWN_TOP_N}'  # nosec B608
    table = engine.execute_sql(query)
    return [
        {
            dimension: label,
            "impressions": int(impressions or 0),
            "clicks": int(clicks or 0),
            "engaged_sessions": int(engaged or 0),
        }
        for label, impressions, clicks, engaged in zip(
            table.column("label_value").to_pylist(),
            table.column("impressions").to_pylist(),
            table.column("clicks").to_pylist(),
            table.column("engaged_sessions").to_pylist(),
        )
    ]


__all__ = ["breakdown_rows"]
