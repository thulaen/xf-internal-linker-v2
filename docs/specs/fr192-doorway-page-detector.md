# FR-192 — Doorway-Page Detector

## Overview
Doorway pages exist purely to redirect visitors to a target destination, typically with thin, templated text and aggressive use of the same anchor terms. They are a top-ten Google webmaster-guideline violation and a reliable spam tell. A small feature vector — text overlap with template, redirect chain length, cloaking flag, and token-repeat ratio — fed into a thresholded decision tree gives a robust per-page detector. Complements `fr054-boilerplate-content-ratio` because boilerplate measures generic header/footer chrome while doorway detection measures targeted templated promotional pages.

## Academic source
Full citation: **Fetterly, D., Manasse, M., & Najork, M. (2004).** "Spam, damn spam, and statistics: Using statistical analysis to locate spam web pages." In *Proceedings of the 7th International Workshop on the Web and Databases (WebDB '04)*, in conjunction with SIGMOD/PODS, Paris, pp. 1-6. DOI: `10.1145/1017074.1017077`.

## Formula
Fetterly, Manasse & Najork (2004), Section 3.2: build a four-feature vector and feed it to a thresholded decision tree:

```
f = (text_overlap, chain_redirect_count, cloaking_flag, token_repeat_ratio)

where
  text_overlap         = max_t∈T  Jaccard(tokens(p), tokens(t))
                         over template family T mined from host
  chain_redirect_count = length of HTTP 3xx + JS-meta-refresh chain leaving p
  cloaking_flag        = 1 iff served HTML to googlebot UA differs from
                         served HTML to default UA by Jaccard < 0.6
  token_repeat_ratio   = max_w (count(w, p) / total_tokens(p))
                         over content tokens (stopwords excluded)
```

Decision tree (Fetterly et al., Table 2):

```
score(p) = 1 if (chain_redirect_count ≥ 2 ∧ text_overlap ≥ 0.7)
              ∨ (cloaking_flag = 1)
              ∨ (token_repeat_ratio ≥ 0.15 ∧ text_overlap ≥ 0.5)
         = 0 otherwise
```

Final ranker contribution: `1 − score(p)`.

## Starting weight preset
```python
"doorway_detector.enabled": "true",
"doorway_detector.ranking_weight": "0.0",
"doorway_detector.text_overlap_threshold": "0.7",
"doorway_detector.token_repeat_threshold": "0.15",
"doorway_detector.cloaking_jaccard": "0.6",
```

## C++ implementation
- File: `backend/extensions/doorway_detector.cpp`
- Entry: `int doorway_score(const PageFeatures& f, const DoorwayThresholds& t)`
- Complexity: O(|tokens|) for token-repeat scan; O(|template_family|) for Jaccard max
- Thread-safety: pure on input slice
- SIMD: AVX2 hash-set Jaccard via 32-bit murmur tokens
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/doorway_detector.py::compute_doorway_score` using `collections.Counter` for token repeat and `set` for Jaccard.

## Benchmark plan

| Size | Tokens | C++ target | Python target |
|---|---|---|---|
| Small | 200 | 0.04 ms | 1 ms |
| Medium | 2,000 | 0.4 ms | 10 ms |
| Large | 20,000 | 4 ms | 100 ms |

## Diagnostics
- Per-page doorway flag (e.g. "Doorway: yes — 3 redirects + 0.82 overlap")
- Per-feature breakdown
- C++/Python badge
- Fallback flag when redirect chain unknown
- Debug fields: `text_overlap`, `chain_redirect_count`, `cloaking_flag`, `token_repeat_ratio`, `top_repeated_token`

## Edge cases & neutral fallback
- Redirect chain not yet crawled → assume 0; fallback flag set
- No template family mined yet → text_overlap = 0
- User-agent variant fetch failed → cloaking_flag = 0
- Single-token "page" (e.g. title-only) → skip signal, return neutral 0.5

## Minimum-data threshold
Page must have ≥ 50 content tokens and a known final HTTP status before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 0.5 MB  ·  RAM: 2 MB (template Jaccard cache)

## Scope boundary vs existing signals
Distinct from `fr054-boilerplate-content-ratio` (generic chrome detection), `fr014-near-duplicate-destination-clustering` (full-page duplicate clustering), and `fr188-spamrank-propagation` (link-graph propagation). Doorway detection is a per-page rule-based classifier on redirect, cloaking, and repetition features.

## Test plan bullets
- Unit: page with 3 redirects + 0.8 overlap returns score = 1
- Unit: clean page with 0 redirects returns score = 0
- Unit: cloaking flag alone triggers score = 1
- Parity: C++ vs Python on 1,000-page fixture within 1e-9
- Edge: redirect chain unknown returns neutral 0.5 with fallback flag
- Edge: page < 50 tokens returns neutral 0.5
- Integration: `1 − score` contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
