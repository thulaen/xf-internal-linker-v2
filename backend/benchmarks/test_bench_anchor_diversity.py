"""Benchmarks for FR-045 anchor diversity scorer.

Measures the batch scorer at 3 input sizes (100 / 1 000 / 5 000 candidates)
through both the C++ fast path and the Python fallback.

Run with:
    pytest backend/benchmarks/test_bench_anchor_diversity.py --benchmark-only

Django settings must be reachable (see benchmarks/conftest.py for the
shared sys.path shim). Academic source for FR-045: Google Search Central
link best-practices + US20110238644A1.
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

from apps.pipeline.services.anchor_diversity import (  # noqa: E402
    AnchorDiversitySettings,
    AnchorHistory,
    evaluate_anchor_diversity_batch,
)
import apps.pipeline.services.anchor_diversity as _ad_mod  # noqa: E402


def _make_inputs(n: int):
    """Build n deterministic per-candidate inputs covering all branches."""
    destination_keys = [(i, "thread") for i in range(n)]
    candidate_anchor_texts = [
        # Rotate between 4 anchors so exact-match counts vary naturally.
        ["weekend camping trip", "sleep gear", "best tent", "winter sleeping bag"][
            i % 4
        ]
        for i in range(n)
    ]
    history_by_destination: dict[tuple[int, str], AnchorHistory] = {}
    for i, key in enumerate(destination_keys):
        # Alternate between insufficient history, below-threshold and
        # concentration cases so the benchmark exercises every branch.
        active = 1 if i % 7 == 0 else 10 + (i % 20)
        before = i % 6
        history_by_destination[key] = AnchorHistory(
            active_anchor_count=active,
            exact_match_counts={candidate_anchor_texts[i]: before},
        )
    return destination_keys, candidate_anchor_texts, history_by_destination


def _settings() -> AnchorDiversitySettings:
    return AnchorDiversitySettings()


@pytest.mark.benchmark(group="anchor-diversity")
@pytest.mark.parametrize("n", [100, 1_000, 5_000])
def test_bench_anchor_diversity_cpp_path(benchmark, n):
    """Exercise the C++ fast path through evaluate_anchor_diversity_batch."""
    destination_keys, candidate_anchor_texts, history_by_destination = _make_inputs(n)
    settings = _settings()

    def run() -> int:
        results = evaluate_anchor_diversity_batch(
            destination_keys=destination_keys,
            candidate_anchor_texts=candidate_anchor_texts,
            history_by_destination=history_by_destination,
            settings=settings,
        )
        return len(results)

    # Use whichever path is available — if the C++ extension is compiled
    # this benchmarks cpp; otherwise it benchmarks Python. The benchmark
    # group name stays the same so runtime comparison is possible.
    result = benchmark(run)
    assert result == n


@pytest.mark.benchmark(group="anchor-diversity")
@pytest.mark.parametrize("n", [100, 1_000, 5_000])
def test_bench_anchor_diversity_python_path(benchmark, n):
    """Force the Python fallback to establish the baseline."""
    destination_keys, candidate_anchor_texts, history_by_destination = _make_inputs(n)
    settings = _settings()
    saved = _ad_mod.HAS_CPP_EXT

    def run() -> int:
        _ad_mod.HAS_CPP_EXT = False
        try:
            results = evaluate_anchor_diversity_batch(
                destination_keys=destination_keys,
                candidate_anchor_texts=candidate_anchor_texts,
                history_by_destination=history_by_destination,
                settings=settings,
            )
        finally:
            _ad_mod.HAS_CPP_EXT = saved
        return len(results)

    result = benchmark(run)
    assert result == n
