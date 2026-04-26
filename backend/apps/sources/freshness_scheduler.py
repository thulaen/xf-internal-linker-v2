"""Crawl-refresh interval calculator (Cho & Garcia-Molina 2003).

Reference: Cho, Junghoo & Garcia-Molina, Hector (2003). "Effective
page refresh policies for Web crawlers." *ACM Transactions on
Database Systems* 28(4): 390-426.

Goal
----
For each URL in the crawl frontier, decide how long to wait before
the next refresh. The input is observational: across the past N
crawls of this URL, how many of them saw a *changed* body. The
output is a recommended interval, clamped to a reasonable range so
a wildly volatile page doesn't get re-fetched every second and a
static page doesn't disappear off the schedule entirely.

Algorithm sketch
----------------

1. Estimate λ (change rate per second) from observed change counts.
   Cho-GM use a Poisson-process estimator with regularisation to
   tolerate zero-change observations:

       λ̂ = -log(1 - p̂)  /  average_interval_seconds
       p̂  = (changes + 1) / (crawls + 2)        # Laplace smoothing

   The ``+1/+2`` bias keeps λ̂ > 0 even when every observation was
   unchanged, so a page that's been static for a week still gets
   re-checked eventually (just with a long interval).

2. Convert λ̂ to a refresh interval. Cho-GM's optimum for maximising
   age-weighted freshness at a fixed crawl budget is roughly:

       optimal_frequency ∝ sqrt(importance * λ̂)
       optimal_interval  ∝ 1 / sqrt(importance * λ̂)

   i.e. pages that change twice as often need to be crawled
   sqrt(2) ≈ 1.4× more frequently, not 2×. Pages that are twice as
   important also get crawled sqrt(2)× more often. Both appear in the
   same product under the square root, which is why the raw interval
   is ``sqrt(1 / (importance * λ̂))``.

3. Clamp to ``[min_interval_seconds, max_interval_seconds]``. On the
   linker's hardware the min is 6 h (a very fresh news page) and
   the max is 30 days (a crystallised archive). Callers can
   override for sitemaps with known publishing cadence.

The module is pure arithmetic — no DB, no I/O. Wiring it into the
crawler's scheduler belongs to a follow-up slice (needs a new
``refresh_interval_seconds`` column on ``CrawledPageMeta`` and
re-queueing logic keyed off ``last_crawled_at + interval``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: 6 h — the project's laptop-sleep-safe floor. No page refreshes
#: more often than this regardless of how volatile it is.
DEFAULT_MIN_INTERVAL_SECONDS: int = 6 * 60 * 60

#: 30 days — above this the refresh becomes a monthly crystal-seed
#: sweep, not a refresh.
DEFAULT_MAX_INTERVAL_SECONDS: int = 30 * 24 * 60 * 60

#: Default cadence for a brand-new URL with zero observations.
#: Long enough to avoid hot-looping on a misconfigured crawl;
#: short enough to learn the page's real volatility within a week.
DEFAULT_BOOTSTRAP_INTERVAL_SECONDS: int = 24 * 60 * 60

#: Default caller-supplied importance weight. 1.0 is neutral; bump
#: this for a site's homepage, drop it for an archive page.
DEFAULT_IMPORTANCE: float = 1.0


@dataclass
class CrawlObservation:
    """Single past-crawl outcome."""

    crawls: int
    changes: int
    average_interval_seconds: float

    def __post_init__(self) -> None:
        if self.crawls < 0:
            raise ValueError("crawls must be >= 0")
        if self.changes < 0:
            raise ValueError("changes must be >= 0")
        if self.changes > self.crawls:
            raise ValueError("changes cannot exceed crawls")
        if self.average_interval_seconds <= 0:
            raise ValueError("average_interval_seconds must be > 0")


@dataclass(frozen=True)
class FreshnessDecision:
    """Output of :func:`next_refresh_interval_seconds`.

    Carries the intermediate estimates so callers can log them for
    debugging without re-running the math.
    """

    interval_seconds: int
    estimated_change_rate_per_second: float
    change_probability: float  # p̂ with Laplace smoothing
    raw_interval_seconds: float  # before clamping
    reason: str


def estimate_change_rate_per_second(
    observation: CrawlObservation,
) -> tuple[float, float]:
    """Return ``(lambda_hat_per_second, change_probability)`` for a URL.

    Uses Laplace smoothing so a 0-change history doesn't produce an
    infinite interval: ``p̂ = (changes + 1) / (crawls + 2)`` is always
    strictly in (0, 1).
    """
    p_hat = (observation.changes + 1) / (observation.crawls + 2)
    # Change-rate λ such that P(change within Δt) = 1 - exp(-λΔt).
    # Rearranging for λ given observed p̂ over Δt: λ = -ln(1 - p̂) / Δt.
    lambda_hat = -math.log(1.0 - p_hat) / observation.average_interval_seconds
    return lambda_hat, p_hat


def next_refresh_interval_seconds(
    observation: CrawlObservation | None,
    *,
    importance: float = DEFAULT_IMPORTANCE,
    min_interval_seconds: int = DEFAULT_MIN_INTERVAL_SECONDS,
    max_interval_seconds: int = DEFAULT_MAX_INTERVAL_SECONDS,
    bootstrap_interval_seconds: int = DEFAULT_BOOTSTRAP_INTERVAL_SECONDS,
) -> FreshnessDecision:
    """Return the recommended interval until the next refresh of a URL.

    Parameters
    ----------
    observation
        Past-crawl summary. ``None`` or zero-crawls returns the
        bootstrap interval.
    importance
        Caller-supplied weight. Square-root law: doubling importance
        shortens the interval by √2.
    min_interval_seconds, max_interval_seconds
        Clamp bounds. The default floor (6 h) prevents the scheduler
        from hot-looping on volatile pages.
    bootstrap_interval_seconds
        Used when we have no prior observations.

    Invariants checked in tests:
      - interval is always in ``[min, max]``.
      - monotonic in change_rate: more frequent changes → shorter
        interval.
      - monotonic in importance: higher importance → shorter interval.
      - a zero-change history still returns a finite (not infinite)
        interval thanks to Laplace smoothing.
    """
    if importance <= 0:
        raise ValueError("importance must be > 0")
    if min_interval_seconds <= 0:
        raise ValueError("min_interval_seconds must be > 0")
    if max_interval_seconds < min_interval_seconds:
        raise ValueError("max_interval_seconds must be >= min_interval_seconds")

    if observation is None or observation.crawls == 0:
        return FreshnessDecision(
            interval_seconds=max(
                min_interval_seconds,
                min(max_interval_seconds, bootstrap_interval_seconds),
            ),
            estimated_change_rate_per_second=0.0,
            change_probability=0.0,
            raw_interval_seconds=float(bootstrap_interval_seconds),
            reason="bootstrap",
        )

    lambda_hat, p_hat = estimate_change_rate_per_second(observation)
    # Cho-GM square-root law for age-weighted freshness-maximising
    # crawl interval. importance appears in the denominator so that
    # higher-importance pages get SHORTER intervals (more frequent
    # crawls), which matches the intent of the weighting.
    raw = math.sqrt(1.0 / (importance * lambda_hat))
    clamped = int(
        max(
            float(min_interval_seconds),
            min(float(max_interval_seconds), raw),
        )
    )
    if clamped == min_interval_seconds:
        reason = "clamped_min"
    elif clamped == max_interval_seconds:
        reason = "clamped_max"
    else:
        reason = "cho_gm_sqrt_law"

    return FreshnessDecision(
        interval_seconds=clamped,
        estimated_change_rate_per_second=lambda_hat,
        change_probability=p_hat,
        raw_interval_seconds=raw,
        reason=reason,
    )
