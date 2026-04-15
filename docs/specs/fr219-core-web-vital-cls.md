# FR-219 - Core Web Vital — Cumulative Layout Shift (CLS)

## Overview
Cumulative Layout Shift quantifies how much visual content unexpectedly moves while a user is reading or interacting with a page. Image elements without explicit dimensions, late-loading ads pushing text down, and font-swap reflows all contribute. Google made CLS a confirmed ranking input in 2021. The signal converts the unitless CLS reading into a `[0, 1]` score using the published "good (≤0.1) / needs-improvement / poor (≥0.25)" thresholds. Used as a small additive bonus on a candidate destination's quality term.

## Academic source
**W3C Web Performance Working Group (2020).** "Layout Instability." W3C Working Draft, originally published April 2020, current draft 2024. URL: `https://www.w3.org/TR/layout-instability/`. Defines the layout-shift entry, impact-fraction × distance-fraction product, session-window aggregation, and the maximum-session-window score (CLSW). **Google Chrome team / web.dev (2020, revised 2021).** "Cumulative Layout Shift (CLS)." URL: `https://web.dev/articles/cls`. Defines the `0.1` good / `0.25` poor thresholds and the session-window methodology used in the formula below.

## Formula
From W3C Layout Instability §3 (layout-shift score) + Google CWV thresholds (2020-2021):

```
For a single layout-shift entry s_j the per-shift score is:

  shift_score(s_j) = impact_fraction(s_j) · distance_fraction(s_j)

where:
  impact_fraction(s_j)   = | union(prev_rect, curr_rect) |  /  | viewport |
  distance_fraction(s_j) = max_displacement_px(s_j)         /  max(viewport_w, viewport_h)

Session-window CLS (W3C-recommended aggregation, max 5s window, 1s gap):

  CLS = max_over_windows W  ( Σ_{s_j ∈ W} shift_score(s_j) )

Signal mapping with GOOD = 0.1, POOR = 0.25:

  signal(CLS) = 1 − clamp((CLS − GOOD) / (POOR − GOOD), 0, 1)
```

Where:
- `prev_rect`, `curr_rect` are the union of unstable-element bounding boxes before and after the frame
- `max_displacement_px` is the largest single-axis movement of any unstable element in the frame
- `CLS ∈ [0, ∞)` — typically `< 1.0` for normal pages
- `signal ∈ [0, 1]` — `1` = sub-0.1 CLS, `0` = above-0.25 CLS, linear in between

## Starting weight preset
```python
"cwv_cls.enabled": "true",
"cwv_cls.ranking_weight": "0.0",
"cwv_cls.good": "0.10",
"cwv_cls.poor": "0.25",
"cwv_cls.session_window_ms": "5000",
"cwv_cls.session_gap_ms": "1000",
"cwv_cls.aggregate": "p75",
"cwv_cls.min_samples": "5",
```

## C++ implementation
- File: `backend/extensions/cwv_cls.cpp`
- Entry: `double cls_score(double cls_value, double good, double poor);` plus session-window aggregator `double cls_max_session_window(const LayoutShift* shifts, int n, double window_ms, double gap_ms);`
- Complexity: `O(n)` over shift list for session-window scan; `O(1)` for score mapping
- Thread-safety: pure functions
- SIMD: not applicable (sequential session-window state machine)
- Builds against pybind11 alongside the other CWV extensions

## Python fallback
`backend/apps/pipeline/services/cwv_cls.py::compute_cls_score(...)` — used when the C++ extension is unavailable; consumes layout-shift entries from headless-render PerformanceObserver (FR-091 stage).

## Benchmark plan
| Shift entries | C++ target | Python target |
|---|---|---|
| 10 | < 0.01 ms | < 0.1 ms |
| 100 | < 0.05 ms | < 1 ms |
| 1000 | < 0.5 ms | < 10 ms |

## Diagnostics
- Raw `CLS` and computed `signal` per page in suggestion detail UI
- Bucket label (`good` / `needs-improvement` / `poor`)
- Number of contributing shift entries and the maximum-impact element (when reported)
- Aggregation method (`mean` / `p75` / `p95`) and sample count
- Whether the worst session window or the cumulative-sum convention was used

## Edge cases & neutral fallback
- No layout-shift entries → CLS = `0.0`, signal = `1.0` (perfect score legitimate)
- `CLS < 0` (impossible) → neutral `0.5`, flag `negative_cls`
- `CLS > 5.0` (one-frame catastrophic shift) → score `0.0`, flag `cls_extreme_clamped`
- User-initiated shift within 500 ms (per W3C §4.2 had-recent-input flag) → excluded from sum
- NaN / Inf → neutral `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` page-load samples (when aggregating across visits) before the score is trusted; below this returns neutral `0.5` with flag `below_min_samples`. Single synthetic-test reading is allowed when `aggregate = mean`.

## Budget
Disk: <1 MB  ·  RAM: <3 MB (shift-entry buffer per page, freed after aggregation)

## Scope boundary vs existing signals
FR-219 does NOT overlap with FR-218 (LCP) or FR-220 (INP) — the three CWVs measure distinct UX axes. It does not overlap with FR-217 (mobile-friendly) which is a static-structural check, not a runtime measurement. The four together form a "performance" cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: CLS=0.0 (1.0), CLS=0.175 (0.5), CLS=0.30 (0.0)
- parity test: C++ vs Python within `1e-6` over 10000 random shift sequences
- adversarial test: had-recent-input shifts correctly excluded, single huge shift clamped
- session-window test: cluster of shifts inside 5s window combined; 1s+ gap starts new window
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: ad-heavy pages (multiple late-loading shifts) score correctly low
