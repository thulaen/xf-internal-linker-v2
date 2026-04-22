"""Benchmarks for 52-pick Source layer helpers (picks #1-#6) — FR-230 / G6.

Covered helpers (PR-C, commit 6d925b1):
- `apps.sources.token_bucket`        — pick #01
- `apps.sources.backoff`             — pick #02
- `apps.sources.circuit_breaker`     — pick #03 (re-export)
- `apps.sources.bloom_filter`        — pick #04
- `apps.sources.hyperloglog`         — pick #05
- `apps.sources.conditional_get`     — pick #06

Three input sizes per helper (small / medium / large) per CLAUDE.md
mandatory-benchmark rule.
"""

from __future__ import annotations

import random

import pytest


# ── Token Bucket (#01) ─────────────────────────────────────────────


def _tokens_workload(n: int, tokens_per_second: float, burst: float):
    from apps.sources.token_bucket import BucketConfig, InMemoryBucketRegistry

    registry = InMemoryBucketRegistry()
    registry.register(
        "bench", BucketConfig(tokens_per_second=tokens_per_second, burst_capacity=burst)
    )
    for _ in range(n):
        registry.try_acquire("bench", cost=1.0)


def test_bench_token_bucket_small(benchmark):
    benchmark(_tokens_workload, 1000, 2.0, 10.0)


def test_bench_token_bucket_medium(benchmark):
    benchmark(_tokens_workload, 100_000, 200.0, 1000.0)


def test_bench_token_bucket_large(benchmark):
    benchmark(_tokens_workload, 1_000_000, 2000.0, 10_000.0)


# ── Backoff + Jitter (#02) ─────────────────────────────────────────


def _draw_jitter_delays(n, rng):
    from apps.sources.backoff import full_jitter_delay

    for attempt in range(n):
        full_jitter_delay(attempt % 10, base=0.5, cap=60.0, rng=rng)


def test_bench_backoff_small(benchmark):
    rng = random.Random(0)
    benchmark(_draw_jitter_delays, 1000, rng)


def test_bench_backoff_medium(benchmark):
    rng = random.Random(0)
    benchmark(_draw_jitter_delays, 100_000, rng)


def test_bench_backoff_large(benchmark):
    rng = random.Random(0)
    benchmark(_draw_jitter_delays, 1_000_000, rng)


# ── Circuit Breaker (#03) ──────────────────────────────────────────


def _trip_breaker_cycle(breaker, n):
    def raising():
        raise RuntimeError("fake")

    for _ in range(n):
        try:
            breaker.call(raising)
        except Exception:
            pass


def test_bench_circuit_breaker_small(benchmark):
    from apps.sources.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(
        name="bench_small",
        failure_threshold=1_000_000,
        recovery_timeout=60,
        expected_exceptions=[RuntimeError],
    )
    benchmark(_trip_breaker_cycle, breaker, 1000)


def test_bench_circuit_breaker_medium(benchmark):
    from apps.sources.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(
        name="bench_medium",
        failure_threshold=1_000_000,
        recovery_timeout=60,
        expected_exceptions=[RuntimeError],
    )
    benchmark(_trip_breaker_cycle, breaker, 100_000)


def test_bench_circuit_breaker_large(benchmark):
    from apps.sources.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(
        name="bench_large",
        failure_threshold=10_000_000,
        recovery_timeout=60,
        expected_exceptions=[RuntimeError],
    )
    benchmark(_trip_breaker_cycle, breaker, 1_000_000)


# ── Bloom Filter (#04) ─────────────────────────────────────────────


def _bloom_populate(bf, items):
    for item in items:
        bf.add(item)


def _bloom_lookup(bf, items):
    for item in items:
        _ = item in bf


def test_bench_bloom_add_small(benchmark):
    from apps.sources.bloom_filter import BloomFilter

    bf = BloomFilter(capacity=10_000, false_positive_rate=0.01)
    items = [f"id-{i}" for i in range(1000)]
    benchmark(_bloom_populate, bf, items)


def test_bench_bloom_add_medium(benchmark):
    from apps.sources.bloom_filter import BloomFilter

    bf = BloomFilter(capacity=1_000_000, false_positive_rate=0.01)
    items = [f"id-{i}" for i in range(100_000)]
    benchmark(_bloom_populate, bf, items)


def test_bench_bloom_contains_large(benchmark):
    from apps.sources.bloom_filter import BloomFilter

    bf = BloomFilter(capacity=1_000_000, false_positive_rate=0.01)
    items = [f"id-{i}" for i in range(100_000)]
    for item in items:
        bf.add(item)
    lookups = [f"id-{i}" for i in range(100_000)]
    benchmark(_bloom_lookup, bf, lookups)


# ── HyperLogLog (#05) ──────────────────────────────────────────────


def _hll_add_many(hll, items):
    for item in items:
        hll.add(item)


def test_bench_hll_small(benchmark):
    from apps.sources.hyperloglog import HyperLogLog

    hll = HyperLogLog(precision=14)
    items = [f"k-{i}" for i in range(1000)]
    benchmark(_hll_add_many, hll, items)


def test_bench_hll_medium(benchmark):
    from apps.sources.hyperloglog import HyperLogLog

    hll = HyperLogLog(precision=14)
    items = [f"k-{i}" for i in range(1_000_000)]
    benchmark(_hll_add_many, hll, items)


def test_bench_hll_count_large(benchmark):
    from apps.sources.hyperloglog import HyperLogLog

    hll = HyperLogLog(precision=14)
    for i in range(1_000_000):
        hll.add(f"k-{i}")
    benchmark(hll.count)


# ── Conditional GET (#06) ──────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=304, headers=None):
        self.status_code = status_code
        self.headers = headers or {
            "ETag": '"abc123"',
            "Last-Modified": "Wed, 22 Apr 2026 12:00:00 GMT",
        }


def _build_and_extract_many(n, etag, lm):
    from apps.sources.conditional_get import (
        build_validator_headers,
        extract_validators,
        is_not_modified,
    )

    resp = _FakeResponse()
    for _ in range(n):
        build_validator_headers(etag=etag, last_modified=lm)
        is_not_modified(resp)
        extract_validators(resp)


def test_bench_conditional_get_small(benchmark):
    benchmark(
        _build_and_extract_many, 10_000, '"abc"', "Wed, 22 Apr 2026 12:00:00 GMT"
    )


def test_bench_conditional_get_medium(benchmark):
    benchmark(
        _build_and_extract_many, 1_000_000, '"abc"', "Wed, 22 Apr 2026 12:00:00 GMT"
    )


def test_bench_conditional_get_large(benchmark):
    benchmark(
        _build_and_extract_many, 10_000_000, '"abc"', "Wed, 22 Apr 2026 12:00:00 GMT"
    )
