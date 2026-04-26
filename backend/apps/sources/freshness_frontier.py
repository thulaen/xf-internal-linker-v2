"""Crawl-frontier freshness gate — pick #10 wiring.

Wraps :mod:`apps.sources.freshness_scheduler` (Cho-Garcia-Molina 2003)
with the Django-side query layer the helper deliberately avoids
owning. The flow:

1. Caller hands in a list of URLs about to be crawled.
2. We bulk-query :class:`CrawledPageMeta` to derive a per-URL history:
   crawl count, distinct content-hash count (= "change" count), the
   newest timestamp, the average gap between observations.
3. We feed each into :func:`freshness_scheduler.next_refresh_interval_seconds`.
4. URLs whose ``time_since_last_crawl < recommended_interval`` are
   added to the skip set.

The helper is opt-in. The crawler calls
:func:`compute_skip_set(urls)` after the robots filter; URLs in the
returned set are dropped from this session's frontier and will land
in a future session whose timing matches their volatility.

Bulk-query design — one DB round-trip regardless of frontier size.
Per-URL queries during frontier construction would be an N+1 disaster.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

from django.utils import timezone

from .freshness_scheduler import (
    CrawlObservation,
    FreshnessDecision,
    next_refresh_interval_seconds,
)

logger = logging.getLogger(__name__)


def compute_skip_set(
    urls: Iterable[str],
    *,
    importance: float = 1.0,
) -> set[str]:
    """Return the subset of *urls* that should be skipped this session.

    A URL is skipped iff:

    - it has at least one prior :class:`CrawledPageMeta` row, **and**
    - the elapsed time since the most recent successful crawl is less
      than the Cho-Garcia-Molina recommended refresh interval.

    URLs without prior history pass through (we crawl every new URL
    at least once). URLs with prior failures (no 200 response) also
    pass through — better to retry than to assume freshness.
    """
    url_list = list(urls)
    if not url_list:
        return set()

    # Bulk query: aggregate per-URL across all CrawledPageMeta rows.
    # We restrict to http_status 200 so failed crawls don't pollute
    # the change-count / interval calculation.

    histories = _load_histories(url_list)
    if not histories:
        return set()

    now = timezone.now()
    skip: set[str] = set()
    for url, history in histories.items():
        decision = _decision_for(history, importance=importance)
        if decision is None:
            continue
        if decision.reason == "bootstrap":
            # No real history yet — let the URL be crawled.
            continue
        elapsed = (now - history.newest_crawl).total_seconds()
        if elapsed < decision.interval_seconds:
            skip.add(url)
            logger.debug(
                "freshness skip: %s (elapsed=%.0fs < interval=%ds, reason=%s)",
                url,
                elapsed,
                decision.interval_seconds,
                decision.reason,
            )
    return skip


# ── Internals ────────────────────────────────────────────────────


class _UrlHistory:
    """Per-URL aggregated stats used to build a CrawlObservation."""

    __slots__ = ("crawl_count", "distinct_hashes", "newest_crawl", "oldest_crawl")

    def __init__(
        self,
        crawl_count: int,
        distinct_hashes: int,
        newest_crawl,
        oldest_crawl,
    ):
        self.crawl_count = crawl_count
        self.distinct_hashes = distinct_hashes
        self.newest_crawl = newest_crawl
        self.oldest_crawl = oldest_crawl


def _load_histories(urls: list[str]) -> dict[str, _UrlHistory]:
    """One bulk query that returns per-URL crawl + change stats."""
    from apps.crawler.models import CrawledPageMeta

    rows = CrawledPageMeta.objects.filter(url__in=urls, http_status=200).values(
        "url", "content_hash", "created_at"
    )
    # Group in Python rather than via ORM aggregation so we can count
    # distinct hashes per URL (Django's `.distinct()` + `.count()` is
    # awkward across multiple aggregates in a single query).
    per_url_hashes: dict[str, set[str]] = defaultdict(set)
    per_url_count: dict[str, int] = defaultdict(int)
    per_url_newest: dict[str, object] = {}
    per_url_oldest: dict[str, object] = {}
    for row in rows:
        url = row["url"]
        per_url_count[url] += 1
        if row["content_hash"]:
            per_url_hashes[url].add(row["content_hash"])
        ts = row["created_at"]
        if ts is None:
            continue
        if url not in per_url_newest or ts > per_url_newest[url]:
            per_url_newest[url] = ts
        if url not in per_url_oldest or ts < per_url_oldest[url]:
            per_url_oldest[url] = ts

    out: dict[str, _UrlHistory] = {}
    for url, count in per_url_count.items():
        if url not in per_url_newest:
            continue
        out[url] = _UrlHistory(
            crawl_count=count,
            distinct_hashes=max(1, len(per_url_hashes.get(url, set())) or 1),
            newest_crawl=per_url_newest[url],
            oldest_crawl=per_url_oldest[url],
        )
    return out


def _decision_for(
    history: _UrlHistory, *, importance: float
) -> FreshnessDecision | None:
    """Translate a per-URL history into a FreshnessDecision."""
    if history.crawl_count <= 0:
        return None
    if history.crawl_count == 1:
        # Single observation → bootstrap interval. The helper handles
        # this branch with an explicit `bootstrap` reason.
        observation = None
    else:
        span = (history.newest_crawl - history.oldest_crawl).total_seconds()
        if span <= 0:
            return None
        average_interval = span / max(1, history.crawl_count - 1)
        # ``distinct_hashes`` counts unique content states. Treat
        # transitions between them as "changes" — at minimum 0
        # (everything identical), at most ``crawl_count``.
        changes = max(0, history.distinct_hashes - 1)
        observation = CrawlObservation(
            crawls=history.crawl_count,
            changes=min(changes, history.crawl_count),
            average_interval_seconds=average_interval,
        )
    return next_refresh_interval_seconds(observation, importance=importance)
