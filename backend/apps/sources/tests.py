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
from .encoding import (
    EncodingGuess,
    decode_with_guess,
    detect_encoding,
    parse_content_type_charset,
)
from .freshness_scheduler import (
    CrawlObservation,
    DEFAULT_BOOTSTRAP_INTERVAL_SECONDS,
    DEFAULT_MAX_INTERVAL_SECONDS,
    DEFAULT_MIN_INTERVAL_SECONDS,
    estimate_change_rate_per_second,
    next_refresh_interval_seconds,
)
from .hyperloglog import HyperLogLog
from .robots import DEFAULT_USER_AGENT, RobotsChecker
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


# ─────────────────────────────────────────────────────────────────────
# Robots.txt parser (PR-D)
# ─────────────────────────────────────────────────────────────────────


class RobotsCheckerTests(SimpleTestCase):
    _ALLOW_ALL = "User-agent: *\nAllow: /\n"
    _DENY_ALL = "User-agent: *\nDisallow: /\n"
    _DENY_SECRET = "User-agent: *\nDisallow: /secret/\n"
    _CRAWL_DELAY = "User-agent: *\nCrawl-delay: 3\n"

    def _checker(self, body: str | None, *, ttl: int = 3600):
        class _Clock:
            def __init__(self) -> None:
                self.t = 100.0

            def __call__(self) -> float:
                return self.t

        self._clock = _Clock()
        fetch_calls: list[str] = []

        def _fetcher(url: str):
            fetch_calls.append(url)
            return body

        checker = RobotsChecker(
            fetcher=_fetcher,
            cache_ttl_seconds=ttl,
            clock=self._clock,
        )
        self._fetch_calls = fetch_calls
        return checker

    def test_missing_robots_allows_everything(self) -> None:
        checker = self._checker(None)
        assert checker.is_allowed("https://example.com/anything") is True

    def test_deny_all_blocks_any_url(self) -> None:
        checker = self._checker(self._DENY_ALL)
        assert checker.is_allowed("https://example.com/index.html") is False
        assert checker.is_allowed("https://example.com/deep/path") is False

    def test_deny_prefix_allows_other_paths(self) -> None:
        checker = self._checker(self._DENY_SECRET)
        assert checker.is_allowed("https://example.com/public/page") is True
        assert checker.is_allowed("https://example.com/secret/page") is False

    def test_cache_hit_does_not_refetch(self) -> None:
        checker = self._checker(self._ALLOW_ALL)
        checker.is_allowed("https://example.com/a")
        checker.is_allowed("https://example.com/b")
        checker.is_allowed("https://example.com/c")
        assert len(self._fetch_calls) == 1

    def test_cache_expires_after_ttl(self) -> None:
        checker = self._checker(self._ALLOW_ALL, ttl=60)
        checker.is_allowed("https://example.com/a")
        self._clock.t += 120
        checker.is_allowed("https://example.com/a")
        assert len(self._fetch_calls) == 2

    def test_crawl_delay_returned_when_declared(self) -> None:
        checker = self._checker(self._CRAWL_DELAY)
        assert checker.crawl_delay("https://example.com/x") == 3.0

    def test_crawl_delay_none_when_absent(self) -> None:
        checker = self._checker(self._ALLOW_ALL)
        assert checker.crawl_delay("https://example.com/x") is None

    def test_malformed_url_returns_allowed(self) -> None:
        checker = self._checker(self._DENY_ALL)
        # URL without a scheme can't be resolved to a robots.txt origin;
        # fail-open keeps the crawler moving.
        assert checker.is_allowed("no-scheme-here") is True

    def test_default_user_agent_is_public(self) -> None:
        assert "XFInternalLinker" in DEFAULT_USER_AGENT


# ─────────────────────────────────────────────────────────────────────
# Encoding detection (PR-D)
# ─────────────────────────────────────────────────────────────────────


class EncodingDetectionTests(SimpleTestCase):
    def test_parse_content_type_charset_happy_path(self) -> None:
        assert parse_content_type_charset("text/html; charset=UTF-8") == "UTF-8"
        assert (
            parse_content_type_charset('text/html; charset="windows-1252"')
            == "windows-1252"
        )

    def test_parse_content_type_charset_missing(self) -> None:
        assert parse_content_type_charset("text/html") is None
        assert parse_content_type_charset("") is None
        assert parse_content_type_charset(None) is None

    def test_header_charset_wins(self) -> None:
        body = "accented".encode("utf-8")
        guess = detect_encoding(body, content_type="text/html; charset=iso-8859-1")
        assert guess.encoding == "iso-8859-1"
        assert guess.source == "header"

    def test_meta_charset_is_used_when_header_absent(self) -> None:
        body = b'<!DOCTYPE html>\n<meta charset="gb18030">\n<p>hello</p>'
        guess = detect_encoding(body)
        assert guess.encoding == "gb18030"
        assert guess.source == "meta"

    def test_utf8_bom_detected(self) -> None:
        body = b"\xef\xbb\xbfplain text"
        guess = detect_encoding(body)
        assert guess.encoding == "utf-8-sig"
        assert guess.source == "bom"

    def test_utf16_le_bom_detected(self) -> None:
        body = b"\xff\xfea\x00"
        guess = detect_encoding(body)
        assert guess.encoding == "utf-16-le"

    def test_plain_utf8_body_returns_decodable(self) -> None:
        body = b"plain ascii and a single char"
        guess = detect_encoding(body)
        decoded = body.decode(guess.encoding, errors="replace")
        assert "plain ascii" in decoded

    def test_empty_body_returns_utf8(self) -> None:
        guess = detect_encoding(b"")
        assert guess.encoding == "utf-8"
        assert guess.source == "empty"

    def test_decode_with_guess_never_raises(self) -> None:
        body = b"\x80\x81\x82\x83"
        text, guess = decode_with_guess(body)
        assert isinstance(text, str)
        assert isinstance(guess, EncodingGuess)

    def test_decode_with_unknown_encoding_falls_back_to_latin1(self) -> None:
        body = b"some bytes"
        text, guess = decode_with_guess(
            body,
            content_type="text/html; charset=notreal-encoding-x123",
        )
        assert isinstance(text, str)
        assert "latin-1" in guess.source


# ─────────────────────────────────────────────────────────────────────
# Freshness scheduler (PR-D)
# ─────────────────────────────────────────────────────────────────────


class FreshnessSchedulerTests(SimpleTestCase):
    def test_bootstrap_when_no_observation(self) -> None:
        decision = next_refresh_interval_seconds(None)
        assert decision.reason == "bootstrap"
        assert decision.interval_seconds == DEFAULT_BOOTSTRAP_INTERVAL_SECONDS

    def test_zero_crawls_is_bootstrap(self) -> None:
        decision = next_refresh_interval_seconds(
            CrawlObservation(crawls=0, changes=0, average_interval_seconds=3600)
        )
        assert decision.reason == "bootstrap"

    def test_invalid_observation_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CrawlObservation(crawls=5, changes=10, average_interval_seconds=60)
        with self.assertRaises(ValueError):
            CrawlObservation(crawls=-1, changes=0, average_interval_seconds=60)
        with self.assertRaises(ValueError):
            CrawlObservation(crawls=1, changes=0, average_interval_seconds=0)

    def test_laplace_smoothing_keeps_zero_change_finite(self) -> None:
        obs = CrawlObservation(crawls=10, changes=0, average_interval_seconds=3600)
        lam, p = estimate_change_rate_per_second(obs)
        assert p > 0.0
        assert lam > 0.0

    def test_high_change_rate_shortens_interval(self) -> None:
        # Loosen the floor so monotonicity is observable (the default
        # 6 h min clamps both short intervals to the same value).
        volatile = CrawlObservation(
            crawls=10, changes=9, average_interval_seconds=3600
        )
        static = CrawlObservation(
            crawls=10, changes=1, average_interval_seconds=3600
        )
        kw = {"min_interval_seconds": 1, "max_interval_seconds": 90 * 24 * 3600}
        volatile_interval = next_refresh_interval_seconds(volatile, **kw).interval_seconds
        static_interval = next_refresh_interval_seconds(static, **kw).interval_seconds
        assert volatile_interval < static_interval

    def test_higher_importance_shortens_interval(self) -> None:
        obs = CrawlObservation(crawls=10, changes=3, average_interval_seconds=3600)
        kw = {"min_interval_seconds": 1, "max_interval_seconds": 365 * 24 * 3600}
        low = next_refresh_interval_seconds(obs, importance=0.25, **kw).interval_seconds
        high = next_refresh_interval_seconds(obs, importance=4.0, **kw).interval_seconds
        assert high < low

    def test_interval_is_clamped_below_min(self) -> None:
        volatile = CrawlObservation(
            crawls=1000, changes=999, average_interval_seconds=60
        )
        decision = next_refresh_interval_seconds(volatile)
        assert decision.interval_seconds == DEFAULT_MIN_INTERVAL_SECONDS
        assert decision.reason == "clamped_min"

    def test_interval_is_clamped_above_max(self) -> None:
        # Very low change rate + very low importance → raw interval
        # pushes past the 30-day ceiling. Crystal page that has been
        # checked 100 times over 7 days each with zero changes, and
        # operator has deprioritised it (importance << 1).
        crystal = CrawlObservation(
            crawls=100,
            changes=0,
            average_interval_seconds=7 * 24 * 3600,
        )
        decision = next_refresh_interval_seconds(crystal, importance=1e-6)
        assert decision.interval_seconds == DEFAULT_MAX_INTERVAL_SECONDS
        assert decision.reason == "clamped_max"

    def test_square_root_law_holds_roughly(self) -> None:
        # raw interval is what we test — clamps in the decision don't
        # affect the underlying sqrt relationship. ratio of raw values
        # should be ~sqrt(2) when change count doubles at fixed cadence.
        slow = CrawlObservation(crawls=100, changes=10, average_interval_seconds=3600)
        fast = CrawlObservation(crawls=100, changes=20, average_interval_seconds=3600)
        slow_dec = next_refresh_interval_seconds(slow, importance=100.0)
        fast_dec = next_refresh_interval_seconds(fast, importance=100.0)
        ratio = slow_dec.raw_interval_seconds / fast_dec.raw_interval_seconds
        # sqrt(2) ≈ 1.41; allow 25% slack for Laplace smoothing distortion.
        assert 1.15 <= ratio <= 1.7

    def test_bad_importance_raises(self) -> None:
        obs = CrawlObservation(crawls=5, changes=1, average_interval_seconds=3600)
        with self.assertRaises(ValueError):
            next_refresh_interval_seconds(obs, importance=0)
        with self.assertRaises(ValueError):
            next_refresh_interval_seconds(obs, importance=-1)
