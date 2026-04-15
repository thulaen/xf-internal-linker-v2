# FR-214 - Alt-Text Coverage Ratio

## Overview
WCAG-compliant `alt` attributes on `<img>` elements are a well-established proxy for editorial quality, accessibility care, and overall page maturity. A page where 100% of images have meaningful alt text is almost always a more carefully maintained page than one where 0% do. The signal counts every `<img>` in the rendered body, counts the subset whose `alt` attribute is non-empty (and not the literal string `"image"` or the filename), and returns the ratio. Pages with no images get a neutral fallback so image-light editorial pages are not penalised. Used as a small additive term on destination quality.

## Academic source
**W3C Web Content Accessibility Guidelines (WCAG) 2.1 (2018).** "Success Criterion 1.1.1 Non-text Content (Level A)." W3C Recommendation, June 5 2018. URL: `https://www.w3.org/TR/WCAG21/#non-text-content`. Defines the alt-text requirement and the empty-alt convention for purely decorative images. **US Patent 9,418,120 B2 (Bjorkegren et al., assigned to Google, 2016).** "Accessibility-based ranking signals for web search." Filed 2014-03-25, granted 2016-08-16. URL: `https://patents.google.com/patent/US9418120B2`. Describes using alt-text coverage and other accessibility-conformance ratios as a quality-side ranking input — the patent basis for treating coverage as a ranker feature.

## Formula
From WCAG 2.1 SC 1.1.1 + US9418120B2 ratio formulation:

```
For images I = {img_1, img_2, ..., img_m} in <body>:

  meaningful(img) = 1   if  alt(img) ≠ ""
                          ∧ alt(img) ≠ basename(src(img))
                          ∧ alt(img) ∉ {"image", "photo", "picture", "img"}
                          ∧ length(alt(img)) ≥ 2 chars
                  = 0   otherwise

  alt_coverage = ( Σ_{img ∈ I} meaningful(img) ) / max(m, 1)

  signal = alt_coverage             if m ≥ min_images
         = 0.5  (neutral)           if m  < min_images
```

Where:
- `alt(img)` = value of the `alt` attribute (empty string if attribute absent)
- `src(img)` = value of `src` (used to detect the lazy "filename as alt" anti-pattern)
- `m` = total `<img>` elements in `<body>` excluding decorative `role="presentation"` images
- `signal ∈ [0, 1]`

## Starting weight preset
```python
"alt_text_coverage.enabled": "true",
"alt_text_coverage.ranking_weight": "0.0",
"alt_text_coverage.min_images": "2",
"alt_text_coverage.exclude_decorative": "true",
"alt_text_coverage.min_alt_chars": "2",
```

## C++ implementation
- File: `backend/extensions/alt_text_coverage.cpp`
- Entry: `double alt_coverage(const char* const* alt_strings, const char* const* src_strings, int m, int min_alt_chars);`
- Complexity: `O(m · L)` where `L` = mean alt length (typically `<` 64 chars)
- Thread-safety: pure function on parallel string arrays
- SIMD: `_mm_cmpestri` for the placeholder-blacklist comparisons
- Builds against pybind11 alongside FR-091 DOM extraction

## Python fallback
`backend/apps/pipeline/services/alt_text_coverage.py::compute_alt_coverage(...)` — invoked from the FR-091 DOM-extraction stage when the C++ extension is unavailable; reuses the `<img>` list BeautifulSoup already builds.

## Benchmark plan
| Images | C++ target | Python target |
|---|---|---|
| 5 | < 0.01 ms | < 0.05 ms |
| 50 | < 0.05 ms | < 0.5 ms |
| 500 | < 0.3 ms | < 5 ms |

## Diagnostics
- Raw `alt_coverage` per page in suggestion detail UI
- Total images, images with meaningful alt, images flagged as filename-only
- List of first 5 offending image src values
- Whether `min_images` floor triggered neutral fallback

## Edge cases & neutral fallback
- Zero images → neutral `0.5`, flag `no_images`
- All decorative (`role="presentation"`) → neutral `0.5`, flag `all_decorative`
- Lazy-loaded images with `data-src` → counted, alt evaluated normally
- SVG `<image>` elements → counted with same rules
- NaN / Inf → impossible (integer counts), defensive clamp returns `0.5`

## Minimum-data threshold
`≥ 2` non-decorative images before the score is trusted; below this returns neutral `0.5` with flag `below_min_images`.

## Budget
Disk: <1 MB  ·  RAM: <2 MB (per-page string arrays, freed after computation)

## Scope boundary vs existing signals
FR-214 does NOT overlap with FR-040 (multimedia boost) — that signal counts media presence as a positive density signal; FR-214 measures the *quality* of accompanying metadata. It does not overlap with FR-213 (heading hierarchy) which scores text-structure correctness. Both feed into a shared accessibility-quality cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: 100% alt page, 0% alt page, mixed-coverage page
- parity test: C++ vs Python within `1e-6` over 1000 sampled pages
- adversarial test: filename-as-alt, single-char alt, lorem-ipsum alt, SVG `<image>`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: image-free editorial pages return neutral, not zero
- decorative test: `role="presentation"` images correctly excluded
