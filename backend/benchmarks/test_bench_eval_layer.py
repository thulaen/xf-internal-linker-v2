"""Benchmarks for 52-pick On-Demand Eval helpers — FR-230 / G6.

Covered shipped helpers (PR-O, commit f25104a):
- `apps.pipeline.services.reservoir_sampling`  — pick #48
- `apps.pipeline.services.shap_explainer`      — pick #47 (on-demand,
                                                 SHAP required)

Kernel SHAP benchmarks are tagged slow and skipped by default; run
explicitly with ``--run-slow``.
"""

from __future__ import annotations

import random

import numpy as np
import pytest


# ── Reservoir Sampling (#48) ──────────────────────────────────────


def _reservoir_once(stream, k, rng):
    from apps.pipeline.services.reservoir_sampling import sample

    sample(stream, k=k, rng=rng)


def test_bench_reservoir_small(benchmark):
    rng = random.Random(0)
    stream = list(range(10_000))
    benchmark(_reservoir_once, stream, 100, rng)


def test_bench_reservoir_medium(benchmark):
    rng = random.Random(0)
    stream = list(range(10_000_000))
    benchmark(_reservoir_once, stream, 1000, rng)


def test_bench_reservoir_large(benchmark):
    rng = random.Random(0)
    # Note: 1B items won't fit in memory; use a generator.
    def _gen():
        for i in range(100_000_000):
            yield i

    benchmark(_reservoir_once, _gen(), 1000, rng)


# ── Kernel SHAP (#47) — slow, on-demand only ──────────────────────


def _shap_available() -> bool:
    try:
        import shap  # noqa: F401
        return True
    except ImportError:
        return False


def _shap_explain(score_fn, subject, background, feature_names, nsamples):
    from apps.pipeline.services.shap_explainer import explain

    explain(
        score_fn=score_fn,
        subject=subject,
        background=background,
        feature_names=feature_names,
        nsamples=nsamples,
    )


def _linear_model(x: np.ndarray) -> np.ndarray:
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    return x @ weights


@pytest.mark.skipif(not _shap_available(), reason="shap not installed")
def test_bench_shap_small(benchmark):
    rng = np.random.default_rng(0)
    subject = rng.uniform(0.0, 1.0, size=4)
    background = rng.uniform(0.0, 1.0, size=(50, 4))
    benchmark(
        _shap_explain,
        _linear_model,
        subject,
        background,
        ["f0", "f1", "f2", "f3"],
        50,
    )


@pytest.mark.skipif(not _shap_available(), reason="shap not installed")
def test_bench_shap_medium(benchmark):
    rng = np.random.default_rng(0)
    subject = rng.uniform(0.0, 1.0, size=4)
    background = rng.uniform(0.0, 1.0, size=(500, 4))
    benchmark(
        _shap_explain,
        _linear_model,
        subject,
        background,
        ["f0", "f1", "f2", "f3"],
        200,
    )


@pytest.mark.skipif(not _shap_available(), reason="shap not installed")
def test_bench_shap_large(benchmark):
    rng = np.random.default_rng(0)

    def _linear_100(x: np.ndarray) -> np.ndarray:
        w = np.linspace(0.01, 1.0, num=100)
        return x @ w

    subject = rng.uniform(0.0, 1.0, size=100)
    background = rng.uniform(0.0, 1.0, size=(1000, 100))
    benchmark(
        _shap_explain,
        _linear_100,
        subject,
        background,
        [f"f{i}" for i in range(100)],
        500,
    )
