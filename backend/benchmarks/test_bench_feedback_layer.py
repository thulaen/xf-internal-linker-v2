"""Benchmarks for 52-pick Feedback helpers — FR-230 / G6.

Covered shipped helpers (PR-N, commit 879ecc5):
- `apps.pipeline.services.ema_aggregator`       — pick #40
- `apps.pipeline.services.cascade_click_model`  — pick #34
- `apps.pipeline.services.position_bias_ips`    — pick #33
- `apps.pipeline.services.elo_rating`           — pick #35
"""

from __future__ import annotations

import random


# ── EMA (#40) ─────────────────────────────────────────────────────


def _ema_batch(series_by_key):
    from apps.pipeline.services.ema_aggregator import ema_per_key

    ema_per_key(series_by_key, alpha=0.1)


def test_bench_ema_small(benchmark):
    rng = random.Random(0)
    data = {f"k{i}": [rng.random() for _ in range(100)] for i in range(10)}
    benchmark(_ema_batch, data)


def test_bench_ema_medium(benchmark):
    rng = random.Random(0)
    data = {f"k{i}": [rng.random() for _ in range(365)] for i in range(1000)}
    benchmark(_ema_batch, data)


def test_bench_ema_large(benchmark):
    rng = random.Random(0)
    data = {f"k{i}": [rng.random() for _ in range(365)] for i in range(10_000)}
    benchmark(_ema_batch, data)


# ── Cascade Click Model (#34) ─────────────────────────────────────


def _cascade_workload(sessions):
    from apps.pipeline.services.cascade_click_model import estimate

    estimate(sessions)


def _make_sessions(n: int, rng: random.Random):
    from apps.pipeline.services.cascade_click_model import ClickSession

    sessions = []
    for _ in range(n):
        docs = [f"d{rng.randint(0, 1000)}" for _ in range(10)]
        clicked = rng.choice([None, 1, 2, 3, 4, 5])
        sessions.append(ClickSession(ranked_docs=docs, clicked_rank=clicked))
    return sessions


def test_bench_cascade_small(benchmark):
    sessions = _make_sessions(100, random.Random(0))
    benchmark(_cascade_workload, sessions)


def test_bench_cascade_medium(benchmark):
    sessions = _make_sessions(100_000, random.Random(0))
    benchmark(_cascade_workload, sessions)


def test_bench_cascade_large(benchmark):
    sessions = _make_sessions(1_000_000, random.Random(0))
    benchmark(_cascade_workload, sessions)


# ── Position-Bias IPS (#33) ───────────────────────────────────────


def _ips_weights_batch(n):
    from apps.pipeline.services.position_bias_ips import ips_weight

    for i in range(n):
        ips_weight(position=1 + (i % 20), eta=1.0, max_weight=10.0)


def test_bench_ips_small(benchmark):
    benchmark(_ips_weights_batch, 1000)


def test_bench_ips_medium(benchmark):
    benchmark(_ips_weights_batch, 100_000)


def test_bench_ips_large(benchmark):
    benchmark(_ips_weights_batch, 10_000_000)


# ── Elo (#35) ─────────────────────────────────────────────────────


def _elo_run(n):
    from apps.pipeline.services.elo_rating import PairwiseOutcome, run_batch

    rng = random.Random(0)
    items = list(range(100))
    outcomes = [
        PairwiseOutcome(
            item_a=rng.choice(items),
            item_b=rng.choice(items),
            score_a=rng.choice([0.0, 0.5, 1.0]),
        )
        for _ in range(n)
    ]
    run_batch(outcomes)


def test_bench_elo_small(benchmark):
    benchmark(_elo_run, 100)


def test_bench_elo_medium(benchmark):
    benchmark(_elo_run, 100_000)


def test_bench_elo_large(benchmark):
    benchmark(_elo_run, 10_000_000)
