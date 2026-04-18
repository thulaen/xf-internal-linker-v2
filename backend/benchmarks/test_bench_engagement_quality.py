"""Benchmarks for ``_compute_engagement_raw_score`` (Phase 3b).

Measures the per-item formula that computes the raw engagement-quality
score from an aggregated telemetry dict. The benchmark calls the pure
function in a tight loop to reflect the inner cost of
``_refresh_engagement_quality_scores`` at 3 input sizes:

- small  =  100 items (typical small site)
- medium = 1_000 items (typical active site)
- large  = 5_000 items (power-user ceiling)

Run with:
    pytest backend/benchmarks/test_bench_engagement_quality.py --benchmark-only

Academic source for the Phase 3b extension: Kim, Hassan, White & Zitouni
(2014) "Modeling dwell time to predict click-level satisfaction" (WSDM).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

_ext_dir = str(Path(__file__).resolve().parent.parent / "extensions")
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

import django  # noqa: E402

django.setup()

import pytest  # noqa: E402

from apps.analytics.sync import _compute_engagement_raw_score  # noqa: E402


def _make_telemetry_rows(n: int) -> list[dict[str, int | float]]:
    """Build n pseudo-realistic aggregated telemetry dicts."""
    rows: list[dict[str, int | float]] = []
    for i in range(n):
        views = 10 + (i % 200)
        sessions = views + (i % 50)
        rows.append(
            {
                "destination_views": views,
                "engaged_sessions": views // 2,
                "bounce_sessions": views // 5,
                "total_engagement_time": float(views * 2),
                "sessions": sessions,
                "quick_exit_sessions": views // 10,
                "dwell_60s_sessions": views // 4,
            }
        )
    return rows


def _run(rows: list[dict[str, int | float]]) -> int:
    scored = 0
    for row in rows:
        if _compute_engagement_raw_score(row) is not None:
            scored += 1
    return scored


@pytest.mark.benchmark(group="engagement-quality")
def test_bench_engagement_quality_small(benchmark) -> None:
    rows = _make_telemetry_rows(100)
    result = benchmark(_run, rows)
    assert result > 0


@pytest.mark.benchmark(group="engagement-quality")
def test_bench_engagement_quality_medium(benchmark) -> None:
    rows = _make_telemetry_rows(1_000)
    result = benchmark(_run, rows)
    assert result > 0


@pytest.mark.benchmark(group="engagement-quality")
def test_bench_engagement_quality_large(benchmark) -> None:
    rows = _make_telemetry_rows(5_000)
    result = benchmark(_run, rows)
    assert result > 0
