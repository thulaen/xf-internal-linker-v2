# FR-217 - Mobile-Friendly Score

## Overview
Since 2015 mobile-friendliness has been a confirmed ranking input at major search engines. The signal evaluates a fixed feature checklist on the rendered HTML/CSS — viewport meta tag, base font size, presence of horizontal scrolling, touch-target sizes, and absence of legacy plug-in content — and returns a weighted-sum score normalised to `[0, 1]`. Used as a small additive bonus on a candidate destination's quality term and as an explicit filter when the operator wants to suppress any non-mobile-friendly destination from the slate.

## Academic source
**US Patent 9,152,714 B1 (Newman, Jaiswal et al., assigned to Google, 2015).** "Crawling and ranking of mobile-friendly webpages." Filed 2012-10-01, granted 2015-10-06. URL: `https://patents.google.com/patent/US9152714B1`. Defines the rule-based feature set (viewport, font size, content-fits-viewport, touch-target spacing, legacy-plugin detection) used as a mobile-friendliness ranking input — the patent basis for the formula below.

## Formula
From US9152714B1 §4 (mobile-friendliness feature set) using the patent's weighted-sum aggregation:

```
Feature checks F = {
  f_viewport     : viewport_meta_present(P) ∧ width="device-width"          weight w_1 = 0.30
  f_font         : base_font_size(P) ≥ 16px                                  weight w_2 = 0.20
  f_no_hscroll   : content_width(P) ≤ viewport_width(P)                      weight w_3 = 0.20
  f_touch        : ratio_touch_targets_≥48×48px(P) ≥ 0.90                    weight w_4 = 0.20
  f_no_plugin    : count(<object>, <embed>, <applet>, .swf) == 0            weight w_5 = 0.10
}

mobile_score(P) = ( Σ_{i=1..5} w_i · f_i(P) ) / ( Σ_{i=1..5} w_i )       ∈ [0, 1]

signal = mobile_score(P)                            if all_checks_runnable
       = 0.5  (neutral)                             if rendering_failed
```

Where:
- `f_i(P) ∈ {0, 1}` for boolean checks; `f_touch` graded `∈ [0, 1]` as the ratio
- weight vector `(0.30, 0.20, 0.20, 0.20, 0.10)` matches the relative emphasis the patent gives to viewport configuration (most critical) versus legacy-plugin presence (least critical in the modern web)
- normalisation by `Σ w_i` keeps `signal ∈ [0, 1]` even if a future weight vector is rebalanced

## Starting weight preset
```python
"mobile_friendly.enabled": "true",
"mobile_friendly.ranking_weight": "0.0",
"mobile_friendly.weight_viewport": "0.30",
"mobile_friendly.weight_font": "0.20",
"mobile_friendly.weight_no_hscroll": "0.20",
"mobile_friendly.weight_touch": "0.20",
"mobile_friendly.weight_no_plugin": "0.10",
"mobile_friendly.min_touch_target_px": "48",
"mobile_friendly.min_font_px": "16",
"mobile_friendly.touch_pass_ratio": "0.90",
```

## C++ implementation
- File: `backend/extensions/mobile_friendly.cpp`
- Entry: `double mobile_score(const MobileFeatures& f, const MobileWeights& w);`
- Complexity: `O(1)` arithmetic on a 5-element feature struct after extraction
- Thread-safety: pure function; weight struct is read-only and shared
- SIMD: not applicable (5-element reduction)
- Builds against pybind11; feature extraction handled in headless-render preprocessing (FR-091 stage)

## Python fallback
`backend/apps/pipeline/services/mobile_friendly.py::compute_mobile_score(...)` — used during FR-091 rendering when the C++ extension is unavailable; relies on `playwright` viewport instrumentation already used by the crawler.

## Benchmark plan
| Mode | C++ target | Python target |
|---|---|---|
| score-only (extracted features) | < 0.001 ms | < 0.01 ms |
| extract + score (per page) | dominated by render (≈ 200 ms) | dominated by render (≈ 200 ms) |

## Diagnostics
- Raw `mobile_score` per page in suggestion detail UI
- Per-feature pass/fail badge with the failing values (e.g. `font_size = 12px`)
- Touch-target pass ratio
- Counts of legacy plug-in elements detected
- Whether headless render succeeded (else neutral fallback)

## Edge cases & neutral fallback
- Headless render failed → neutral `0.5`, flag `render_failed`
- Page returned non-HTML content-type → neutral `0.5`, flag `non_html`
- Zero touch targets on page (text-only article) → `f_touch = 1.0`, flag `no_touch_targets_neutral`
- Viewport meta present with `user-scalable=no` → counted as fail (accessibility regression), flag `user_scalable_no`
- NaN / Inf → impossible (bounded features), defensive clamp returns `0.5`

## Minimum-data threshold
Successful headless render is the only prerequisite; no document-count threshold applies because the score is intra-page.

## Budget
Disk: <1 MB  ·  RAM: <5 MB (feature struct per page, render handled by FR-091 budget)

## Scope boundary vs existing signals
FR-217 does NOT overlap with FR-218 (LCP), FR-219 (CLS), or FR-220 (INP) — those are runtime performance metrics, FR-217 is a static-structural mobile-readiness check. It does not overlap with FR-052 (readability) which scores prose, not viewport behaviour. The four mobile/CWV signals form a "mobile-experience" cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: ideal mobile page (1.0), desktop-only page (0.0), partial-mobile page
- parity test: C++ vs Python within `1e-6` on extracted feature vectors
- adversarial test: viewport with `width=1024`, `<embed>` Flash content, 8px font
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: rendered pages with `user-scalable=no` correctly downgraded
- render-failure test: HTTP 5xx pages correctly return neutral with flag
