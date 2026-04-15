# FR-213 - Heading Hierarchy Correctness

## Overview
Well-formed heading nesting (`<h1>` then `<h2>` then `<h3>` and so on, never skipping a level) is a strong proxy for editorial care, accessibility quality, and crawler comprehensibility. Pages whose authors thought about document outline tend to be the ones whose authors also thought about content. The signal walks the DOM heading tree depth-first and computes the fraction of headings whose level is at most one greater than the closest enclosing heading's level. A perfectly nested page scores `1.0`; a page that jumps from `<h1>` straight to `<h4>` everywhere scores near `0.0`. Used as a small additive bonus on a candidate destination's quality term in the ranker.

## Academic source
**W3C HTML Living Standard / HTML5 (2014).** "4.3 Sections — The sectioning model and outline algorithm." W3C Recommendation, October 28 2014. URL: `https://www.w3.org/TR/html5/sections.html`. Defines the heading-level rank rules (`h1`..`h6`) and the rank-based outline construction this signal validates against. **Nagappan, Nachiappan; Williams, Laurie; Vouk, Mladen; Osborne, John (2006).** "Using In-Process Testing Metrics to Estimate Post-Release Field Quality." *Proceedings of the 28th International Conference on Software Engineering (ICSE 2006)*, IEEE, pp. 209-218. DOI: `10.1109/ICSE.2006.1638253` — establishes structural-correctness ratios as predictive quality metrics, the methodological basis for `valid_count / total_count`.

## Formula
From W3C HTML5 §4.3 sectioning model + Nagappan et al. (2006) ratio formulation:

```
For headings H = [h_1, h_2, ..., h_n] in DOM document order, with level(h_i) ∈ {1..6}:

  parent(h_i) = argmax_{j < i} { level(h_j) < level(h_i) }

  valid(h_i) = 1   if  level(h_i) ≤ level(parent(h_i)) + 1
             = 1   if  i = 1 and level(h_1) ∈ {1, 2}
             = 0   otherwise

  hierarchy_correctness =  ( Σ_{i=1..n} valid(h_i) ) / max(n, 1)
```

Where:
- `level(h_i)` = numeric rank from the tag (`<h1>` → 1, `<h6>` → 6)
- `parent(h_i)` = closest preceding heading whose rank is strictly less than `h_i`'s rank (depth-first traversal of the implicit outline)
- `n` = total heading count in `<body>` (excluding `<header>`/`<footer>` boilerplate)
- Score `∈ [0, 1]` — `1` = every nested heading respects rank-plus-one rule

## Starting weight preset
```python
"heading_hierarchy.enabled": "true",
"heading_hierarchy.ranking_weight": "0.0",   # inert until validated
"heading_hierarchy.exclude_zones": "header,footer,nav,aside",
"heading_hierarchy.min_headings": "3",
```

## C++ implementation
- File: `backend/extensions/heading_hierarchy.cpp`
- Entry: `double hierarchy_correctness(const uint8_t* heading_levels, int n);`
- Complexity: `O(n)` single pass with a stack of parent levels
- Thread-safety: pure function on a level-array buffer
- SIMD: not applicable — branchy traversal, but fits in L1 for any realistic page
- Builds against pybind11 like other DOM-feature extensions (FR-091 family)

## Python fallback
`backend/apps/pipeline/services/heading_hierarchy.py::compute_hierarchy_score(...)` — used during crawl-time DOM extraction (FR-091) when the C++ extension is unavailable; reuses BeautifulSoup heading list already built for FR-091.

## Benchmark plan
| Headings | C++ target | Python target |
|---|---|---|
| 10 | < 0.01 ms | < 0.1 ms |
| 100 | < 0.05 ms | < 1 ms |
| 1000 | < 0.5 ms | < 10 ms |

## Diagnostics
- Raw `hierarchy_correctness` per page in suggestion detail UI
- Heading-level sequence shown as `[1, 2, 2, 3, 5]` with offending levels highlighted
- Count of valid vs invalid headings
- Whether `min_headings` floor was triggered (neutral fallback)

## Edge cases & neutral fallback
- Zero headings → neutral `0.5`, flag `no_headings`
- Single heading at any level → score `1.0` only if level ∈ {1, 2}, else `0.0`
- Multiple `<h1>` allowed (HTML5 sectioning) — only counted invalid if outside a new sectioning root
- Headings with no text content → ignored, flag `empty_heading_skipped`
- NaN / Inf → impossible (integer levels), but defensive clamp returns `0.5`

## Minimum-data threshold
`≥ 3` headings in the body before the score is trusted; below this returns neutral `0.5` with flag `below_min_headings`.

## Budget
Disk: <1 MB  ·  RAM: <2 MB (level-array per page, freed after computation)

## Scope boundary vs existing signals
FR-213 does NOT overlap with FR-098 (dominant-passage centrality) — that signal looks at body-text positional emphasis, not heading nesting. It does not overlap with FR-058 (n-gram writing quality) which scores prose, not document outline. It complements FR-052 (readability-level matching) by adding a structural quality axis to a lexical quality axis.

## Test plan bullets
- unit tests: perfectly nested page (score 1.0), all-`<h1>` page, jump from h1→h4 page
- parity test: C++ vs Python within `1e-6` over 1000 sampled pages
- adversarial test: ASCII-art h1s, hidden headings (`display:none`), heading-only navs
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: pages with `<section>`/`<article>` sectioning roots score correctly
- minimum-data test: 1- and 2-heading pages return neutral with flag set
