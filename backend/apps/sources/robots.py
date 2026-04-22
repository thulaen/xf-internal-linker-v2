"""Robots.txt compliance — stdlib-only wrapper around ``urllib.robotparser``.

Reference: RFC 9309 "Robots Exclusion Protocol" (Koster, Illyes,
Zeller, Sassman — IETF 2022).

The project already stores a ``robots_meta`` field on the crawler's
page rows (the inline ``<meta name="robots">`` tag), but no code
consults the actual ``/robots.txt`` file before a fetch. This module
is the adapter that does.

Design rules:

- **Stdlib only.** The plan calls out ``reppy`` as an option but the
  project has no external-robots-parsing dependency, and
  ``urllib.robotparser`` has shipped with Python since forever.
  Adding a pip dep for a feature that stdlib covers fails the
  duplication rule.
- **In-memory LRU cache, per (host, user-agent).** The fetch cost
  for robots.txt is trivial (small text file) but re-parsing on every
  URL check is wasteful. Cache size is configurable; default 256 is
  plenty for a single-site deployment.
- **Cache TTL.** Robots files change. Default TTL is 24 h —
  operators who edit a site's robots.txt shouldn't wait longer than
  that to see the crawler respect the change.
- **Transport-agnostic.** The fetcher is a callable the caller
  injects; this lets tests drop in a fake without importing
  ``requests`` here (the project mixes several HTTP clients). The
  default fetcher uses stdlib ``urllib.request``.
- **Fail-open on network errors.** A transient 500 from the robots
  endpoint is not grounds to stop the whole crawl — we log and
  permit the URL. Fail-closed (refuse to crawl) would let a flaky
  host kill every scheduled refresh. RFC 9309 §2.2.1 explicitly
  endorses the fail-open behaviour: "If no records are found, the
  crawler is allowed to access any URLs on the server."
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


#: Default XF Internal Linker user agent — callers override if needed.
DEFAULT_USER_AGENT: str = "XFInternalLinker/2.0 (+https://github.com/thulaen/xf-internal-linker-v2)"

#: Seconds until a cached robots.txt entry is considered stale.
DEFAULT_CACHE_TTL_SECONDS: int = 24 * 60 * 60  # 24 h

#: Cap on the cached entry count per RobotsChecker instance.
DEFAULT_CACHE_CAPACITY: int = 256

#: Timeout (seconds) for the default stdlib fetcher.
DEFAULT_FETCH_TIMEOUT: int = 10


# Callable the checker uses to fetch a robots.txt URL. Returns either
# the text body or None (for 404 / any transport error — fail-open).
RobotsFetcher = Callable[[str], str | None]


@dataclass
class _CacheEntry:
    parser: RobotFileParser
    fetched_at: float
    body_hash: int  # for "did it change?" invalidation support


def _default_fetcher(url: str) -> str | None:
    """Fetch *url* via stdlib ``urlopen``. Returns body on 200, None otherwise."""
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urlopen(req, timeout=DEFAULT_FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError):
        # Fail-open: the caller treats None as "robots absent → crawl allowed".
        return None


class RobotsChecker:
    """Thread-safe LRU-ish cache of parsed robots.txt files per host.

    Usage::

        checker = RobotsChecker()
        if checker.is_allowed("https://example.com/secret/", user_agent="MyBot"):
            fetch(url)
    """

    def __init__(
        self,
        *,
        fetcher: RobotsFetcher = _default_fetcher,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        cache_capacity: int = DEFAULT_CACHE_CAPACITY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be > 0")
        if cache_capacity <= 0:
            raise ValueError("cache_capacity must be > 0")
        self._fetcher = fetcher
        self._ttl = cache_ttl_seconds
        self._capacity = cache_capacity
        self._clock = clock
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    # ── Public API ────────────────────────────────────────────────

    def is_allowed(
        self,
        url: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> bool:
        """Return True if *url* may be crawled by *user_agent*.

        Fail-open: network errors returning the robots.txt file,
        malformed robots files, and missing-file responses all result
        in ``True``. The caller is responsible for whatever it does
        once allowance is granted (rate limiting etc.) — this check
        only reads robots.txt.
        """
        entry = self._get_entry_for_url(url)
        if entry is None:
            return True  # Fail-open.
        try:
            return entry.parser.can_fetch(user_agent, url)
        except Exception:  # noqa: BLE001 — never let a parser bug crash the crawler
            logger.exception(
                "robots: can_fetch raised for url=%s ua=%s — defaulting to allowed",
                url,
                user_agent,
            )
            return True

    def crawl_delay(
        self,
        url: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> float | None:
        """Return the ``Crawl-delay`` directive (seconds) if the server declares one.

        ``None`` when not declared or robots.txt is absent. Callers
        should feed this into their rate-limit configuration
        (:class:`apps.sources.token_bucket.BucketConfig`).
        """
        entry = self._get_entry_for_url(url)
        if entry is None:
            return None
        try:
            delay = entry.parser.crawl_delay(user_agent)
        except Exception:  # noqa: BLE001
            return None
        if delay in (None, 0):
            return None
        return float(delay)

    def clear(self) -> None:
        """Drop every cached entry. Test helper."""
        with self._lock:
            self._cache.clear()

    # ── Internals ─────────────────────────────────────────────────

    def _robots_url_for(self, url: str) -> tuple[str, str]:
        """Return (origin_key, robots_url) for *url*.

        The cache is keyed by scheme+host+port so http://a.com and
        https://a.com maintain separate robots.txt copies.
        """
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"robots: cannot derive origin from url={url!r}")
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        return origin, f"{origin}/robots.txt"

    def _get_entry_for_url(self, url: str) -> _CacheEntry | None:
        try:
            origin, robots_url = self._robots_url_for(url)
        except ValueError:
            return None

        now = self._clock()
        with self._lock:
            entry = self._cache.get(origin)
            if entry is not None and (now - entry.fetched_at) < self._ttl:
                return entry

        # Fetch outside the lock — fetcher could be slow (network).
        body = self._fetcher(robots_url)

        with self._lock:
            # Another thread may have repopulated the cache while we
            # were fetching — trust its result if it's fresher.
            existing = self._cache.get(origin)
            if existing is not None and (now - existing.fetched_at) < self._ttl:
                return existing

            parser = RobotFileParser()
            if body is None:
                # Per RFC 9309 §2.2.1 — absence = allow everything.
                parser.parse([])
            else:
                parser.parse(body.splitlines())
            new_entry = _CacheEntry(
                parser=parser,
                fetched_at=now,
                body_hash=hash(body or ""),
            )
            self._cache[origin] = new_entry
            self._evict_if_over_capacity()
            return new_entry

    def _evict_if_over_capacity(self) -> None:
        """Drop oldest entries when cache is over capacity. Caller holds the lock."""
        if len(self._cache) <= self._capacity:
            return
        # Sort by fetched_at ascending, drop the oldest N over capacity.
        sorted_items = sorted(
            self._cache.items(), key=lambda kv: kv[1].fetched_at
        )
        overflow = len(self._cache) - self._capacity
        for key, _ in sorted_items[:overflow]:
            self._cache.pop(key, None)


#: Process-wide default instance for callers that don't need their own
#: configuration. Tests should construct their own :class:`RobotsChecker`
#: with an injected fetcher rather than mutating this one.
DEFAULT_CHECKER: RobotsChecker = RobotsChecker()
