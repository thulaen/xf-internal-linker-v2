"""Benchmarks for 52-pick Crawl & Import helpers (picks #9-#11) — FR-230 / G6.

Covered helpers (PR-D, commit f8548e4):
- `apps.sources.robots`                — pick #09
- `apps.sources.encoding`              — pick #11
- `apps.sources.freshness_scheduler`   — pick #10

Picks #07 Trafilatura, #08 URL Canonicalisation, #12 SHA-256 are not
benchmarked here:
- #07 deferred (no helper shipped).
- #08 not yet written (to-ship, see pick-08 spec).
- #12 partial — inline in site_crawler.py (helper extraction pending W2).
"""

from __future__ import annotations

import pytest


# ── Robots.txt (#09) ──────────────────────────────────────────────


def _robots_batch(checker, urls):
    for url in urls:
        checker.is_allowed(url)


@pytest.fixture
def robots_checker_offline():
    """A RobotsChecker whose fetcher returns an allow-all policy."""
    from apps.sources.robots import RobotsChecker

    def fetch_allow_all(url):
        return "User-agent: *\nAllow: /\n"

    return RobotsChecker(fetcher=fetch_allow_all)


def test_bench_robots_small(benchmark, robots_checker_offline):
    urls = [f"https://site-{i % 10}.example/page-{i}" for i in range(100)]
    benchmark(_robots_batch, robots_checker_offline, urls)


def test_bench_robots_medium(benchmark, robots_checker_offline):
    urls = [f"https://site-{i % 100}.example/page-{i}" for i in range(10_000)]
    benchmark(_robots_batch, robots_checker_offline, urls)


def test_bench_robots_large(benchmark, robots_checker_offline):
    urls = [f"https://site-{i % 1000}.example/page-{i}" for i in range(100_000)]
    benchmark(_robots_batch, robots_checker_offline, urls)


# ── Encoding detection (#11) ──────────────────────────────────────


def _detect_batch(bodies, headers):
    from apps.sources.encoding import detect_encoding

    for body, header in zip(bodies, headers):
        detect_encoding(body, content_type_header=header)


def test_bench_encoding_small(benchmark):
    bodies = [f"Body {i} café".encode("utf-8") for i in range(100)]
    headers = ["text/html; charset=utf-8"] * 100
    benchmark(_detect_batch, bodies, headers)


def test_bench_encoding_medium(benchmark):
    bodies = [f"Body {i} café".encode("utf-8") for i in range(10_000)]
    headers = ["text/html; charset=utf-8"] * 10_000
    benchmark(_detect_batch, bodies, headers)


def test_bench_encoding_large(benchmark):
    # Mix of encodings to exercise full cascade path.
    import random

    rng = random.Random(42)
    bodies = []
    for i in range(100_000):
        if i % 3 == 0:
            bodies.append(f"content {i} €".encode("utf-8"))
        elif i % 3 == 1:
            bodies.append(f"content {i}".encode("latin-1"))
        else:
            bodies.append(b"\xff\xfe" + f"content {i}".encode("utf-16-le"))
    headers = [None] * 100_000
    benchmark(_detect_batch, bodies, headers)


# ── Freshness scheduler (#10) ─────────────────────────────────────


def _freshness_scores(observations):
    from apps.sources.freshness_scheduler import (
        CrawlObservation,
        next_refresh_interval_seconds,
    )

    for crawls, changes, avg_interval in observations:
        obs = CrawlObservation(
            crawls=crawls, changes=changes, average_interval_seconds=avg_interval
        )
        next_refresh_interval_seconds(obs, importance=1.0)


def test_bench_freshness_small(benchmark):
    import random

    rng = random.Random(0)
    obs = [
        (rng.randint(0, 50), rng.randint(0, 50), rng.uniform(60, 86400))
        for _ in range(1000)
    ]
    # Ensure changes <= crawls.
    obs = [(c, min(c, ch), a) for c, ch, a in obs]
    benchmark(_freshness_scores, obs)


def test_bench_freshness_medium(benchmark):
    import random

    rng = random.Random(0)
    obs = [
        (rng.randint(0, 50), rng.randint(0, 50), rng.uniform(60, 86400))
        for _ in range(100_000)
    ]
    obs = [(c, min(c, ch), a) for c, ch, a in obs]
    benchmark(_freshness_scores, obs)


def test_bench_freshness_large(benchmark):
    import random

    rng = random.Random(0)
    obs = [
        (rng.randint(0, 50), rng.randint(0, 50), rng.uniform(60, 86400))
        for _ in range(1_000_000)
    ]
    obs = [(c, min(c, ch), a) for c, ch, a in obs]
    benchmark(_freshness_scores, obs)
