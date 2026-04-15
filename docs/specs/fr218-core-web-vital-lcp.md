# FR-218 - Core Web Vital — Largest Contentful Paint (LCP)

## Overview
Largest Contentful Paint measures the wall-clock time from navigation start until the largest above-the-fold image or text block paints. Google made it a confirmed ranking input in 2021. Pages whose largest hero element appears within 2.5s feel responsive; pages where it takes more than 4s feel broken. The signal converts the raw LCP millisecond reading into a `[0, 1]` score using the published "good / needs-improvement / poor" thresholds. Used as a small additive bonus on a candidate destination's quality term.

## Academic source
**W3C Web Performance Working Group (2020).** "Largest Contentful Paint." W3C Working Draft, originally published April 2020, current draft 2024. URL: `https://www.w3.org/TR/largest-contentful-paint/`. Defines the LCP measurement algorithm — element selection, candidate ranking by intrinsic size, and the report-on-input-or-scroll contract. **Google Chrome team / web.dev (2020).** "Largest Contentful Paint (LCP)." URL: `https://web.dev/articles/lcp`. Defines the `2500 ms` good / `4000 ms` poor thresholds used in the formula below.

## Formula
From W3C LCP §6 (reporting algorithm) + Google CWV thresholds (2020):

```
Let lcp_ms = LCP value reported by the W3C `largest-contentful-paint` PerformanceObserver entry.
Let GOOD = 2500 ms, POOR = 4000 ms.

  signal(lcp_ms) = 1                                          if lcp_ms ≤ GOOD
                 = 1 − (lcp_ms − GOOD) / (POOR − GOOD)        if GOOD < lcp_ms ≤ POOR
                 = 0                                          if lcp_ms > POOR

equivalently:

  signal(lcp_ms) = 1 − clamp((lcp_ms − GOOD) / (POOR − GOOD), 0, 1)
```

Where:
- `lcp_ms ∈ ℝ⁺` — milliseconds since `navigationStart` to the largest contentful paint
- `GOOD = 2500 ms`, `POOR = 4000 ms` per Google's published thresholds
- `signal ∈ [0, 1]` — `1` = sub-2.5s LCP, `0` = above-4s LCP, linear in between
- if multiple LCP samples per page (real-user-monitoring), the signal uses the 75th-percentile reading per CWV reporting convention

## Starting weight preset
```python
"cwv_lcp.enabled": "true",
"cwv_lcp.ranking_weight": "0.0",
"cwv_lcp.good_ms": "2500",
"cwv_lcp.poor_ms": "4000",
"cwv_lcp.aggregate": "p75",          # one of mean | p75 | p95
"cwv_lcp.min_samples": "5",
```

## C++ implementation
- File: `backend/extensions/cwv_lcp.cpp`
- Entry: `double lcp_score(double lcp_ms, double good_ms, double poor_ms);` plus `double lcp_p75(const double* samples, int n);`
- Complexity: `O(1)` arithmetic; `O(n log n)` for percentile when aggregating samples
- Thread-safety: pure functions
- SIMD: not applicable (scalar reduction)
- Builds against pybind11 alongside the other CWV extensions

## Python fallback
`backend/apps/pipeline/services/cwv_lcp.py::compute_lcp_score(...)` — used when the C++ extension is unavailable; consumes LCP samples sourced from a headless-render PerformanceObserver during FR-091 crawl.

## Benchmark plan
| Samples | C++ target | Python target |
|---|---|---|
| 1 | < 0.001 ms | < 0.005 ms |
| 100 | < 0.01 ms | < 0.1 ms |
| 10000 | < 1 ms | < 50 ms |

## Diagnostics
- Raw `lcp_ms` and computed `signal` per page in suggestion detail UI
- Bucket label (`good` / `needs-improvement` / `poor`) per CWV convention
- Sample count and aggregation method used (`mean` / `p75` / `p95`)
- LCP-element selector (image src or text snippet) when reported by the observer

## Edge cases & neutral fallback
- No LCP entry reported (e.g. page navigated away before paint) → neutral `0.5`, flag `no_lcp_entry`
- `lcp_ms < 0` (clock skew) → neutral `0.5`, flag `negative_lcp`
- `lcp_ms > 60000` (one-minute outlier, likely a stalled page) → score `0.0`, flag `lcp_extreme_clamped`
- Sample count below `min_samples` → neutral `0.5`, flag `below_min_samples`
- NaN / Inf → neutral `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` LCP samples (when aggregating) before the score is trusted; below this returns neutral `0.5` with flag `below_min_samples`. Single synthetic-test reading is allowed when `aggregate = mean` and crawl is the source.

## Budget
Disk: <1 MB  ·  RAM: <2 MB (sample buffer per page, freed after percentile)

## Scope boundary vs existing signals
FR-218 does NOT overlap with FR-219 (CLS) or FR-220 (INP) — the three CWVs measure distinct user-experience axes (paint speed, visual stability, input responsiveness). It does not overlap with FR-217 (mobile-friendly) which is a static-structural check. The four together form a "performance" cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: 2000ms (1.0), 3250ms (0.5), 5000ms (0.0)
- parity test: C++ vs Python within `1e-6` over 10000 random LCP values
- adversarial test: negative, NaN, Inf, 60s+ samples
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: percentile aggregation matches numpy reference within 1 ms
- threshold-config test: changing `good_ms` / `poor_ms` shifts score curve as expected
