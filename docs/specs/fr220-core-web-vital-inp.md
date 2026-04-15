# FR-220 - Core Web Vital — Interaction to Next Paint (INP)

## Overview
Interaction to Next Paint replaced First Input Delay as a Core Web Vital in March 2024. INP measures, across the entire page lifetime, the latency from a user interaction (click, tap, key press) until the next frame is painted reflecting the response. Unlike FID it captures *all* interactions, not just the first, and uses a near-worst-case 98th-percentile aggregation. The signal converts the raw INP millisecond reading into a `[0, 1]` score using the published "good (≤200ms) / needs-improvement / poor (≥500ms)" thresholds. Used as a small additive bonus on a candidate destination's quality term.

## Academic source
**W3C Web Performance Working Group (2024).** "Event Timing API — Interaction to Next Paint." W3C Working Draft, March 2024. URL: `https://www.w3.org/TR/event-timing/`. Defines the per-interaction latency measurement (input-to-next-paint) and the per-interaction-id grouping that INP rolls up. **Google Chrome team / web.dev (2024).** "Interaction to Next Paint (INP)." URL: `https://web.dev/articles/inp`. Defines the 98th-percentile aggregation across all interactions in a page lifetime, the `200 ms` good / `500 ms` poor thresholds, and the rationale for replacing FID.

## Formula
From W3C Event Timing §5 (interaction grouping) + Google CWV INP thresholds (2024):

```
For each interaction I_k on the page:
  latency(I_k) = max_over_event_entries_e_in_I_k ( e.endTime − e.startTime )

Aggregation across all interactions in the page lifetime:
  K = total interaction count
  if K  < 50:    INP = max_k latency(I_k)              (worst-case over few interactions)
  if K ≥ 50:    INP = quantile_{0.98}( {latency(I_k)} )

Signal mapping with GOOD = 200 ms, POOR = 500 ms:
  signal(INP) = 1 − clamp((INP − GOOD) / (POOR − GOOD), 0, 1)
```

Where:
- `e.startTime`, `e.endTime` from the W3C Event Timing API for each event entry inside an interaction
- "interaction" groups all event entries sharing the same `interactionId`
- `K < 50` → use max (per Google's published convention for low-interaction pages); `K ≥ 50` → use 98th-percentile
- `INP ∈ ℝ⁺` milliseconds; `signal ∈ [0, 1]` — `1` = sub-200ms INP, `0` = above-500ms INP

## Starting weight preset
```python
"cwv_inp.enabled": "true",
"cwv_inp.ranking_weight": "0.0",
"cwv_inp.good_ms": "200",
"cwv_inp.poor_ms": "500",
"cwv_inp.percentile": "0.98",
"cwv_inp.high_interaction_threshold": "50",
"cwv_inp.min_interactions": "1",
```

## C++ implementation
- File: `backend/extensions/cwv_inp.cpp`
- Entry: `double inp_score(double inp_ms, double good_ms, double poor_ms);` plus quantile reducer `double inp_aggregate(const double* latencies, int n, double q, int high_threshold);`
- Complexity: `O(1)` for score mapping; `O(n log n)` for quantile (or `O(n)` for nth_element-based selection)
- Thread-safety: pure functions
- SIMD: not applicable (sequential percentile)
- Builds against pybind11 alongside the other CWV extensions

## Python fallback
`backend/apps/pipeline/services/cwv_inp.py::compute_inp_score(...)` — used when the C++ extension is unavailable; consumes Event-Timing entries from headless-render PerformanceObserver during FR-091 stage.

## Benchmark plan
| Interactions | C++ target | Python target |
|---|---|---|
| 10 | < 0.01 ms | < 0.1 ms |
| 100 | < 0.05 ms | < 1 ms |
| 10000 | < 1 ms | < 50 ms |

## Diagnostics
- Raw `INP` and computed `signal` per page in suggestion detail UI
- Bucket label (`good` / `needs-improvement` / `poor`)
- Aggregation method actually used (`max` for K<50, `p98` for K≥50)
- Total interaction count `K`
- Worst-interaction event-type breakdown (click / keydown / pointerdown) when reported

## Edge cases & neutral fallback
- Zero interactions on the page → neutral `0.5`, flag `no_interactions` (page may be too short-lived to score)
- `INP < 0` → neutral `0.5`, flag `negative_inp`
- `INP > 30000` ms (frozen tab outlier) → score `0.0`, flag `inp_extreme_clamped`
- Sample count below `min_interactions` → neutral `0.5`, flag `below_min`
- NaN / Inf → neutral `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 1` interaction before the score is trusted; below this returns neutral `0.5` with flag `no_interactions`. Real-world rollup typically waits for `K ≥ 50` per Google's RUM guidance before the p98 aggregation kicks in; below `K = 50` the signal uses the max-latency convention.

## Budget
Disk: <1 MB  ·  RAM: <3 MB (latency buffer per page, freed after aggregation)

## Scope boundary vs existing signals
FR-220 does NOT overlap with FR-218 (LCP) or FR-219 (CLS). FR-220 specifically replaces the deprecated FID metric — there is no separate FID signal in this repo. It does not overlap with FR-217 (mobile-friendly) which is a static-structural check. The four together form a "performance" cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: 100ms (1.0), 350ms (0.5), 600ms (0.0)
- parity test: C++ vs Python within `1e-6` over 10000 random latency arrays
- aggregation test: K=10 uses max, K=100 uses p98, both within 1ms of numpy reference
- adversarial test: negative, NaN, Inf, 30s+ outliers
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: zero-interaction pages return neutral, not zero
