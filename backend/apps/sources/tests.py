"""Tests for the PR-C source-layer helpers.

Kept Django-agnostic where possible (the helpers themselves depend
only on the stdlib), but collected in a ``TestCase`` so they pick up
the project's test runner conventions.
"""

from __future__ import annotations

import random
import time

from django.test import SimpleTestCase, TestCase

from .backoff import full_jitter_delay, retry, retry_context
from .bloom_filter import BloomFilter, optimal_params
from .circuit_breaker import (
    CircuitBreaker,
    xenforo_breaker,
)
from .conditional_get import (
    STATUS_NOT_MODIFIED,
    build_validator_headers,
    extract_validators,
    is_not_modified,
)
from .hyperloglog import HyperLogLog
from .token_bucket import (
    DEFAULT_REGISTRY,
    BucketConfig,
    InMemoryBucketRegistry,
)


# ─────────────────────────────────────────────────────────────────────
# Token bucket
# ─────────────────────────────────────────────────────────────────────


class TokenBucketTests(SimpleTestCase):
    def setUp(self) -> None:
        self.reg = InMemoryBucketRegistry()

    def test_try_acquire_respects_burst_then_refuses(self) -> None:
        self.reg.register(
            "xenforo:hosta",
            BucketConfig(tokens_per_second=1.0, burst_capacity=3.0),
        )
        # Three immediate acquires allowed (burst size).
        for _ in range(3):
            assert self.reg.try_acquire("xenforo:hosta") is True
        # Fourth without refill time must fail.
        assert self.reg.try_acquire("xenforo:hosta") is False

    def test_refill_is_linear_in_elapsed_time(self) -> None:
        self.reg.register(
            "wp:hostb",
            BucketConfig(tokens_per_second=10.0, burst_capacity=10.0),
        )
        for _ in range(10):
            self.reg.try_acquire("wp:hostb")
        # Wait long enough for 2 tokens (0.2 s at 10 tps).
        time.sleep(0.25)
        assert self.reg.try_acquire("wp:hostb") is True
        assert self.reg.try_acquire("wp:hostb") is True
        # But not a third immediately.
        assert self.reg.try_acquire("wp:hostb") is False

    def test_wait_and_acquire_waits_then_succeeds(self) -> None:
        self.reg.register(
            "host-wait",
            BucketConfig(tokens_per_second=20.0, burst_capacity=1.0),
        )
        self.reg.try_acquire("host-wait")  # drain
        start = time.monotonic()
        acquired = self.reg.wait_and_acquire("host-wait", timeout=1.0)
        elapsed = time.monotonic() - start
        assert acquired is True
        # 20 tps → ~50 ms wait. Allow a wide margin for CI latency.
        assert 0.01 <= elapsed <= 0.5

    def test_wait_and_acquire_times_out(self) -> None:
        self.reg.register(
            "host-timeout",
            BucketConfig(tokens_per_second=1.0, burst_capacity=1.0),
        )
        self.reg.try_acquire("host-timeout")
        # 1 token/sec, want 10 tokens, timeout 0.05 s — must refuse.
        assert (
            self.reg.wait_and_acquire("host-timeout", cost=10.0, timeout=0.05)
            is False
        )

    def test_unknown_key_uses_safe_default(self) -> None:
        # Never registered — default is 1 tps, burst 1.
        assert self.reg.try_acquire("unregistered-host") is True
        assert self.reg.try_acquire("unregistered-host") is False

    def test_invalid_config_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BucketConfig(tokens_per_second=0.0, burst_capacity=1.0)
        with self.assertRaises(ValueError):
            BucketConfig(tokens_per_second=1.0, burst_capacity=-1.0)

    def test_zero_or_negative_cost_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.try_acquire("whatever", cost=0)

    def test_default_registry_clear_isolates_tests(self) -> None:
        DEFAULT_REGISTRY.register(
            "shared",
            BucketConfig(tokens_per_second=5.0, burst_capacity=2.0),
        )
        assert DEFAULT_REGISTRY.try_acquire("shared") is True
        DEFAULT_REGISTRY.clear()
        # After clear, key returns to the unknown-default 1/1.
        assert DEFAULT_REGISTRY.available("shared") <= 1.0


# ─────────────────────────────────────────────────────────────────────
# Backoff + jitter
# ─────────────────────────────────────────────────────────────────────


class FullJitterDelayTests(SimpleTestCase):
    def test_returns_zero_upper_bound_at_attempt_zero(self) -> None:
        rng = random.Random(0)
        delay = full_jitter_delay(0, base=1.0, cap=10.0, rng=rng)
        # Uniform in [0, base=1.0].
        assert 0.0 <= delay <= 1.0

    def test_cap_bounds_delay_at_large_attempts(self) -> None:
        rng = random.Random(0)
        for attempt in range(5, 12):
            delay = full_jitter_delay(attempt, base=1.0, cap=2.0, rng=rng)
            assert 0.0 <= delay <= 2.0

    def test_negative_attempt_rejected(self) -> None:
        with self.assertRaises(ValueError):
            full_jitter_delay(-1)


class RetryHelperTests(SimpleTestCase):
    def test_success_first_try_no_sleep(self) -> None:
        sleep_calls: list[float] = []

        def ok():
            return "done"

        result = retry(ok, sleep=sleep_calls.append, max_attempts=3)
        assert result == "done"
        assert sleep_calls == []

    def test_retries_transient_then_succeeds(self) -> None:
        state = {"n": 0}
        sleep_calls: list[float] = []

        def flaky():
            state["n"] += 1
            if state["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        result = retry(
            flaky,
            retryable=lambda exc: isinstance(exc, ConnectionError),
            sleep=sleep_calls.append,
            rng=random.Random(42),
            max_attempts=5,
        )
        assert result == "ok"
        assert state["n"] == 3
        # Two sleeps for two retries.
        assert len(sleep_calls) == 2

    def test_non_retryable_raises_immediately(self) -> None:
        sleep_calls: list[float] = []

        def fatal():
            raise ValueError("nope")

        with self.assertRaises(ValueError):
            retry(
                fatal,
                retryable=lambda exc: isinstance(exc, ConnectionError),
                sleep=sleep_calls.append,
            )
        assert sleep_calls == []

    def test_gives_up_after_max_attempts(self) -> None:
        sleep_calls: list[float] = []

        def always_bad():
            raise ConnectionError("persistent")

        with self.assertRaises(ConnectionError):
            retry(
                always_bad,
                retryable=lambda exc: True,
                max_attempts=3,
                sleep=sleep_calls.append,
                rng=random.Random(0),
            )
        # 2 sleeps because the final attempt raises without sleeping.
        assert len(sleep_calls) == 2

    def test_on_retry_hook_fires(self) -> None:
        hook_calls: list[tuple[int, BaseException, float]] = []

        def flaky():
            raise ConnectionError("x")

        with self.assertRaises(ConnectionError):
            retry(
                flaky,
                retryable=lambda exc: True,
                max_attempts=3,
                sleep=lambda _s: None,
                rng=random.Random(0),
                on_retry=lambda i, exc, d: hook_calls.append((i, exc, d)),
            )
        assert len(hook_calls) == 2
        assert all(isinstance(c[1], ConnectionError) for c in hook_calls)


class RetryContextTests(SimpleTestCase):
    def test_yields_attempt_indices_and_sleeps_between(self) -> None:
        sleep_calls: list[float] = []
        attempts_seen: list[int] = []
        for attempt in retry_context(
            max_attempts=3, sleep=sleep_calls.append, rng=random.Random(0)
        ):
            attempts_seen.append(attempt)
        assert attempts_seen == [0, 1, 2]
        # Two sleeps — before yield 1 and before yield 2.
        assert len(sleep_calls) == 2


# ─────────────────────────────────────────────────────────────────────
# Circuit breaker re-export
# ─────────────────────────────────────────────────────────────────────


class CircuitBreakerReExportTests(SimpleTestCase):
    def test_reexported_class_is_the_pipeline_class(self) -> None:
        from apps.pipeline.services.circuit_breaker import (
            CircuitBreaker as UpstreamBreaker,
        )

        assert CircuitBreaker is UpstreamBreaker

    def test_preconfigured_instances_available(self) -> None:
        # Sanity: the instances exist and are CircuitBreaker subtypes.
        assert isinstance(xenforo_breaker, CircuitBreaker)


# ─────────────────────────────────────────────────────────────────────
# Bloom filter
# ─────────────────────────────────────────────────────────────────────


class BloomFilterTests(SimpleTestCase):
    def test_optimal_params_matches_published_formula(self) -> None:
        num_bits, num_hashes = optimal_params(1_000_000, 0.01)
        # ~9.6 bits per element at 1% FP — ~9.58M bits, ~7 hashes.
        assert 9_000_000 <= num_bits <= 10_500_000
        assert 6 <= num_hashes <= 8

    def test_add_then_contains(self) -> None:
        bf = BloomFilter(capacity=10_000, false_positive_rate=0.01)
        bf.add("xf:thread:42")
        bf.add(b"binary-key")
        bf.add(9001)

        assert "xf:thread:42" in bf
        assert b"binary-key" in bf
        assert 9001 in bf

    def test_absent_keys_rejected(self) -> None:
        bf = BloomFilter(capacity=10_000, false_positive_rate=0.001)
        bf.update([f"id:{i}" for i in range(100)])
        # Keys never added — FP rate is 0.1% so one miss in 1000 is the
        # worst case; 50 tries is safe.
        misses = sum(1 for i in range(50) if f"unseen:{i}" in bf)
        assert misses <= 1

    def test_cardinality_estimate_is_reasonable(self) -> None:
        bf = BloomFilter(capacity=10_000, false_positive_rate=0.01)
        bf.update(range(5_000))
        estimate = len(bf)
        # Accept ± 25% — the Swamidass-Baldi estimator is noisy.
        assert 3_500 <= estimate <= 6_500

    def test_clear_empties_filter(self) -> None:
        bf = BloomFilter(capacity=1_000, false_positive_rate=0.01)
        bf.update(range(500))
        bf.clear()
        assert 1 not in bf
        assert 499 not in bf
        assert len(bf) == 0

    def test_rejects_unsupported_key_type(self) -> None:
        bf = BloomFilter(capacity=100, false_positive_rate=0.01)
        with self.assertRaises(TypeError):
            bf.add(object())  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────
# HyperLogLog
# ─────────────────────────────────────────────────────────────────────


class HyperLogLogTests(SimpleTestCase):
    def test_empty_sketch_counts_zero(self) -> None:
        assert HyperLogLog(precision=10).count() == 0

    def test_precision_bounds_enforced(self) -> None:
        with self.assertRaises(ValueError):
            HyperLogLog(precision=3)
        with self.assertRaises(ValueError):
            HyperLogLog(precision=17)

    def test_counts_small_cardinality_exactly(self) -> None:
        # Below 2.5 * m the linear-counting correction kicks in and
        # typically nails small cardinalities exactly.
        hll = HyperLogLog(precision=10)  # m = 1024
        for i in range(100):
            hll.add(f"post-{i}")
        assert 90 <= hll.count() <= 110

    def test_counts_medium_cardinality_within_3_percent(self) -> None:
        hll = HyperLogLog(precision=14)  # m = 16384, std err ~0.81%
        for i in range(100_000):
            hll.add(f"id-{i}")
        est = hll.count()
        # 3 standard errors = 99.7% of runs.
        assert 97_000 <= est <= 103_000

    def test_merge_combines_two_sketches(self) -> None:
        a = HyperLogLog(precision=10)
        b = HyperLogLog(precision=10)
        for i in range(500):
            a.add(f"x-{i}")
        for i in range(300, 800):
            b.add(f"x-{i}")
        a.merge(b)
        est = a.count()
        # Union is 800 distinct elements, precision 10 → std err ~3.3%.
        assert 720 <= est <= 880

    def test_merge_rejects_different_precision(self) -> None:
        a = HyperLogLog(precision=10)
        b = HyperLogLog(precision=12)
        with self.assertRaises(ValueError):
            a.merge(b)

    def test_clear_resets_count(self) -> None:
        hll = HyperLogLog(precision=8)
        for i in range(200):
            hll.add(i)
        hll.clear()
        assert hll.count() == 0

    def test_byte_size_scales_with_precision(self) -> None:
        # Sanity: precision 14 → ~16 KB sketch.
        hll = HyperLogLog(precision=14)
        assert hll.byte_size == 1 << 14


# ─────────────────────────────────────────────────────────────────────
# Conditional GET
# ─────────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Minimal stand-in for a requests/httpx Response."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class _AiohttpStyleResponse:
    """aiohttp names the field `status`, not `status_code`."""

    def __init__(self, status: int, headers: dict[str, str] | None = None):
        self.status = status
        self.headers = headers or {}


class ConditionalGetTests(SimpleTestCase):
    def test_build_validator_headers_with_both(self) -> None:
        h = build_validator_headers(
            etag='"abc123"',
            last_modified="Sun, 21 Apr 2026 10:00:00 GMT",
        )
        assert h == {
            "If-None-Match": '"abc123"',
            "If-Modified-Since": "Sun, 21 Apr 2026 10:00:00 GMT",
        }

    def test_build_validator_headers_with_only_etag(self) -> None:
        h = build_validator_headers(etag='"abc123"', last_modified=None)
        assert h == {"If-None-Match": '"abc123"'}

    def test_build_validator_headers_ignores_empty_inputs(self) -> None:
        h = build_validator_headers(etag="  ", last_modified="")
        assert h == {}

    def test_is_not_modified_on_304(self) -> None:
        resp = _FakeResponse(status_code=STATUS_NOT_MODIFIED)
        assert is_not_modified(resp) is True

    def test_is_not_modified_on_200(self) -> None:
        resp = _FakeResponse(status_code=200)
        assert is_not_modified(resp) is False

    def test_is_not_modified_accepts_aiohttp_shape(self) -> None:
        resp = _AiohttpStyleResponse(status=304)
        assert is_not_modified(resp) is True

    def test_extract_validators_case_insensitive(self) -> None:
        resp = _FakeResponse(
            status_code=200,
            headers={
                "etag": '"new-tag"',
                "Last-Modified": "Mon, 22 Apr 2026 12:00:00 GMT",
            },
        )
        out = extract_validators(resp)
        assert out == {
            "etag": '"new-tag"',
            "last_modified": "Mon, 22 Apr 2026 12:00:00 GMT",
        }

    def test_extract_validators_returns_empty_when_absent(self) -> None:
        resp = _FakeResponse(status_code=200, headers={"content-type": "text/html"})
        assert extract_validators(resp) == {}

    def test_is_not_modified_rejects_weird_response(self) -> None:
        class NoStatus:
            pass

        with self.assertRaises(TypeError):
            is_not_modified(NoStatus())
