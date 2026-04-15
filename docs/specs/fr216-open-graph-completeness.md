# FR-216 - Open Graph Tag Completeness

## Overview
Open Graph tags drive how a page renders when shared on Facebook, LinkedIn, Slack, and most social platforms. Pages with complete OG metadata are typically pages whose authors care about distribution — a strong proxy for editorial intent. The signal scans `<meta property="og:*">` and `<meta name="twitter:*">` tags, scores the presence and validity of the five recommended OG fields (`og:title`, `og:type`, `og:image`, `og:url`, `og:description`) plus optional Twitter Card supplements, and returns a normalised completeness score. Used as a small additive bonus on destination quality.

## Academic source
**Facebook / Meta (2010).** "The Open Graph protocol." Open standard maintained by Facebook, version 1.0 published August 11 2010, current revision 2014. URL: `https://ogp.me/`. Defines the five required OG fields and the typed-object extension model this signal evaluates. **Twitter / X (2012).** "Twitter Cards Markup Reference." URL: `https://developer.x.com/en/docs/x-for-websites/cards/overview/markup`. Defines `twitter:card`, `twitter:site`, `twitter:title`, `twitter:description`, `twitter:image` — the supplementary fields scored as a validity bonus.

## Formula
From OG Protocol §1 (required fields) + Twitter Cards spec (supplementary fields):

```
Required OG field set R = {og:title, og:type, og:image, og:url, og:description}
Supplementary set    S = {twitter:card, twitter:title, twitter:image, og:site_name, og:locale}

For page P:
  present_R(P) = | { f ∈ R : meta_value(P, f) ≠ "" } |
  valid_R(P)   = | { f ∈ R : valid(meta_value(P, f), f) } |   (URL-form, length, type-enum checks)
  bonus_S(P)   = | { f ∈ S : meta_value(P, f) ≠ "" } |  /  |S|

  base_score = (present_R(P) + valid_R(P)) / (2 · |R|)        ∈ [0, 1]
  signal     = clamp(base_score · 0.85 + bonus_S(P) · 0.15, 0, 1)
```

Where:
- `valid(v, og:url)` ⇔ `v` matches RFC 3986 absolute-URL grammar
- `valid(v, og:image)` ⇔ `v` is absolute URL with image extension or content-type fetched OK
- `valid(v, og:type)` ⇔ `v` ∈ OG type vocabulary `{article, website, book, profile, video.*, music.*, ...}`
- `valid(v, og:title)` ⇔ `2 ≤ length(v) ≤ 200`
- `valid(v, og:description)` ⇔ `10 ≤ length(v) ≤ 500`
- `signal ∈ [0, 1]`; `1.0` = all five required fields present + valid + full Twitter complement

## Starting weight preset
```python
"open_graph_completeness.enabled": "true",
"open_graph_completeness.ranking_weight": "0.0",
"open_graph_completeness.required_weight": "0.85",
"open_graph_completeness.supplementary_weight": "0.15",
"open_graph_completeness.validate_image_fetch": "false",   # network call optional
```

## C++ implementation
- File: `backend/extensions/open_graph_completeness.cpp`
- Entry: `double og_completeness(const OGTag* tags, int n, bool validate_image_fetch);`
- Complexity: `O(n)` linear scan over tag list; `O(1)` lookups against required/supplementary sets
- Thread-safety: pure function on tag-array buffer
- SIMD: `_mm_cmpestri` for OG-type-enum membership tests
- Builds against pybind11 alongside FR-091 DOM extraction

## Python fallback
`backend/apps/pipeline/services/open_graph.py::compute_og_score(...)` — used during FR-091 DOM extraction when the C++ extension is unavailable; reuses BeautifulSoup `<meta>` list already built.

## Benchmark plan
| Tags | C++ target | Python target |
|---|---|---|
| 5 | < 0.01 ms | < 0.05 ms |
| 20 | < 0.05 ms | < 0.5 ms |
| 100 | < 0.2 ms | < 2 ms |

## Diagnostics
- Raw `signal` per page in suggestion detail UI
- Per-required-field present/valid badge
- Bonus contribution from Twitter supplementary tags
- List of missing required fields and validation failures
- Whether image-fetch validation was skipped (network-cost gate)

## Edge cases & neutral fallback
- Zero `<meta property="og:*">` tags → neutral `0.5`, flag `no_og_tags`
- Field present but empty string → counted as absent, flag `empty_field`
- Duplicate field (multiple `og:image`) → first valid one wins, flag `duplicate_field`
- Relative URL in `og:url` / `og:image` → fails validity, flag `relative_url`
- NaN / Inf → impossible (integer counts), defensive clamp returns `0.5`

## Minimum-data threshold
`≥ 1` `og:*` tag before the score is trusted; below this returns neutral `0.5` with flag `no_og_tags`.

## Budget
Disk: <1 MB  ·  RAM: <2 MB (per-page tag buffer, freed after computation)

## Scope boundary vs existing signals
FR-216 does NOT overlap with FR-215 (Schema.org completeness) — OG and Schema.org are independent vocabularies. It does not overlap with FR-039 (entity salience) which scores entity *recurrence*; FR-216 scores metadata *coverage*. It also does not overlap with FR-090 (cross-platform engagement) which uses *behavioral* social signals; FR-216 uses *structural* social-readiness signals.

## Test plan bullets
- unit tests: full OG + Twitter (1.0), only `og:title` (0.17), no tags (neutral 0.5)
- parity test: C++ vs Python within `1e-6` over 1000 sampled pages
- adversarial test: relative URLs, type-enum violations, duplicate `og:image`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: pages with only Twitter Cards but no OG return correct mid-range score
- network-validation test: when `validate_image_fetch = true`, broken image URLs flagged
