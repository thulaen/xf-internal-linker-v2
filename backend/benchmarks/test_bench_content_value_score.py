"""Benchmarks for ``compute_content_value_raw`` (Phase 3a).

Measures the per-item formula that computes the raw content-value score
from aggregated GA4/Matomo/GSC signals. The benchmark calls the pure
function in a tight loop to reflect the inner cost of
``_refresh_content_value_scores`` at 3 input sizes:

- small  =  100 items (typical small site)
- medium = 1_000 items (typical active site)
- large  = 5_000 items (power-user ceiling)

Run with:
    pytest backend/benchmarks/test_bench_content_value_score.py --benchmark-only

Academic source for the Phase 3a extension: Kim, Hassan, White & Zitouni
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

from apps.analytics.sync import compute_content_value_raw  # noqa: E402


def _make_inputs(n: int) -> list[dict[str, int | float]]:
    """Build n pseudo-realistic aggregated signals with deterministic values."""
    inputs: list[dict[str, int | float]] = []
    for i in range(n):
        views = 10 + (i % 200)
        inputs.append(
            {
                "gsc_clicks": i % 50,
                "gsc_ctr": (i % 10) * 0.01,
                "gsc_impressions": 100 + (i % 500),
                "destination_views": views,
                "engaged_sessions": views // 3,
                "conversions": i % 7,
                "telemetry_clicks": i % 40,
                "quick_exit_sessions": views // 10,
                "dwell_60s_sessions": views // 5,
            }
        )
    return inputs


def _run(inputs: list[dict[str, int | float]]) -> int:
    scored = 0
    for row in inputs:
        if compute_content_value_raw(**row) is not None:
            scored += 1
    return scored


@pytest.mark.benchmark(group="content-value")
def test_bench_content_value_raw_small(benchmark) -> None:
    inputs = _make_inputs(100)
    result = benchmark(_run, inputs)
    assert result > 0


@pytest.mark.benchmark(group="content-value")
def test_bench_content_value_raw_medium(benchmark) -> None:
    inputs = _make_inputs(1_000)
    result = benchmark(_run, inputs)
    assert result > 0


@pytest.mark.benchmark(group="content-value")
def test_bench_content_value_raw_large(benchmark) -> None:
    inputs = _make_inputs(5_000)
    result = benchmark(_run, inputs)
    assert result > 0
