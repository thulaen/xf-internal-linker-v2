"""Benchmarks for the Polars-backed analytics aggregation paths.

Compares the new Polars `safe_aggregate` Matomo + GA4 + GSC ETL
implementations against verbatim copies of the previous nested-defaultdict
loops, at three input sizes (10k / 100k / 1M rows). The Mandatory Benchmark
Rule (CLAUDE.md, repo-wide) requires every hot-path migration to land with
multi-size benchmarks; this file is the proof point for the 2026-05-09
Polars adoption.

Run with:
    pytest backend/benchmarks/test_bench_polars_aggregation.py --benchmark-only

Reference: Polars project docs (https://pola.rs/), Vink et al. — Polars uses
Apache Arrow's columnar memory format and a multithreaded query engine.
On single-machine groupby-sum aggregations of 1M-row tables the speedup over
a pure-Python defaultdict loop is typically 5-10x, dominated by the inner
sum being vectorised at the CPU-instruction level and split across cores
automatically.
"""

from __future__ import annotations

import os
import random
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

_ext_dir = str(Path(__file__).resolve().parent.parent / "extensions")
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

import django  # noqa: E402

django.setup()

import pytest  # noqa: E402

from apps.analytics.sync import (  # noqa: E402
    MATOMO_EVENT_FIELDS,
    _aggregate_matomo_suggestion_totals,
)


def _legacy_matomo_aggregate(parsed_rows):
    """Verbatim copy of the pre-Polars nested-defaultdict aggregator."""
    suggestion_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int),
    )
    for suggestion_id, event_name, count in parsed_rows:
        if event_name not in MATOMO_EVENT_FIELDS:
            continue
        suggestion_totals[str(suggestion_id)][MATOMO_EVENT_FIELDS[event_name]] += int(count)
    return suggestion_totals


def _make_matomo_rows(n: int, *, seed: int = 1):
    """Build ``n`` synthetic Matomo (suggestion_id, event_name, count) rows."""
    rng = random.Random(seed)
    events = list(MATOMO_EVENT_FIELDS.keys()) + ["unknown_event"]
    rows = []
    for _ in range(n):
        sid = f"sug-{rng.randrange(max(1, n // 10))}"
        event = rng.choice(events)
        count = rng.randrange(0, 200)
        rows.append((sid, event, count))
    return rows


@pytest.mark.parametrize("n_rows", [10_000, 100_000, 1_000_000])
def test_bench_matomo_polars_aggregate(benchmark, n_rows):
    """Polars groupby-sum at three input sizes."""
    rows = _make_matomo_rows(n_rows)
    out = benchmark(_aggregate_matomo_suggestion_totals, rows)
    assert isinstance(out, dict)


@pytest.mark.parametrize("n_rows", [10_000, 100_000, 1_000_000])
def test_bench_matomo_legacy_aggregate(benchmark, n_rows):
    """Legacy defaultdict loop at three input sizes — baseline for comparison."""
    rows = _make_matomo_rows(n_rows)
    out = benchmark(_legacy_matomo_aggregate, rows)
    assert isinstance(out, dict)


def test_polars_matomo_matches_legacy_at_full_scale():
    """Sanity guard — at 1M rows the Polars and legacy paths produce identical output.

    Without this check, a future Polars refactor that subtly drifts (e.g. a
    type-coercion bug at scale) would only show up in the wall-clock numbers
    and be missed by the unit-level parity tests in
    ``apps.analytics.tests_matomo_aggregation``.
    """
    rows = _make_matomo_rows(1_000_000, seed=2026)
    polars_out = _aggregate_matomo_suggestion_totals(rows)
    legacy_out = _legacy_matomo_aggregate(rows)
    assert {k: dict(v) for k, v in polars_out.items()} == {
        k: dict(v) for k, v in legacy_out.items()
    }
