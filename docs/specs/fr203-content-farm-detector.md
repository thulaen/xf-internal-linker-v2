# FR-203 - Content-Farm Detector

## Overview
A "content farm" is a site or sub-forum that publishes a very large number of shallow, low-quality pages cheaply, usually targeting long-tail search demand. The Lin, Liu and Xue (2013) approach combines three site-level signals — average per-page quality, total page count, and average crawl depth — into a single farm score. We adapt this to forum sub-corpora (per author, per category, per imported batch). Used as a multiplicative penalty so candidates from a high-farm-score source rank below organic content.

## Academic source
**Lin, Yu-Ru; Liu, Tie-Yan; Xue, Gui-Rong (2013).** "Detecting Content Farms in Web Search." *Proceedings of the 22nd International Conference on World Wide Web (WWW 2013) Companion Volume*, pp. 219-220 (poster) and full paper presented in WWW 2013 Adversarial IR track. The three-signal multiplicative score in §3 — page count × depth-shallowness × low-quality-topic-share — is the basis for this signal.

## Formula
For each source `s` (author / category / import batch) compute three components:

**Component 1 — low-quality-topic share** (LDA topic distribution against curated low-quality topic set `T_lq`):
```
lqts(s) = Σ_{z ∈ T_lq}  P(z | s)                  ∈ [0, 1]
```

**Component 2 — page-count factor** (large source = more farm-like):
```
pcf(s) = log(1 + |pages(s)|) / log(1 + N_max)     ∈ [0, 1]
```

**Component 3 — shallow-depth factor** (low average crawl depth from site root):
```
sdf(s) = max(0, 1 − avg_depth(s) / depth_norm),   depth_norm = 4   ∈ [0, 1]
```

Combined score (paper Eq. 5):
```
farm_score(s) = lqts(s) · pcf(s) · sdf(s)
farm_penalty(c) = farm_score(source(c))           applied per candidate c
```

## Starting weight preset
```python
"content_farm.enabled": "true",
"content_farm.ranking_weight": "0.0",
"content_farm.lda_topic_count": "100",
"content_farm.lq_topic_path": "data/low_quality_topics.json",
"content_farm.depth_norm": "4.0",
"content_farm.n_max": "10000",
```

## C++ implementation
- File: `backend/extensions/content_farm.cpp`
- Entry: `void compute_farm_scores(const SourceStats* sources, int n_sources, const LdaModel& lda, double* out_score);`
- Complexity: `O(n_sources · K)` where `K` = LDA topic count
- Thread-safety: per-source computation parallelised via OpenMP
- LDA inference is delegated to Python (gensim) on cold-load only; per-call uses cached `P(z | s)` matrix
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/content_farm.py::compute_farm(...)` — uses `gensim.models.LdaModel` and `numpy` for the topic mass aggregation.

## Benchmark plan
| Sources | C++ target | Python target |
|---|---|---|
| 100 | < 5 ms | < 100 ms |
| 1 K | < 50 ms | < 1 s |
| 10 K | < 500 ms | < 10 s |

## Diagnostics
- Per-source `lqts`, `pcf`, `sdf`, and combined `farm_score`
- Top-3 contributing low-quality topics per source
- Histogram of `farm_score` across sources
- LDA model checksum and topic-set version
- C++ vs Python badge

## Edge cases & neutral fallback
- Source with `< 10` pages → neutral `0.0`, flag `source_too_small`
- LDA model not yet trained → neutral `0.0`, flag `lda_not_ready`
- Average depth `> depth_norm` → `sdf = 0` (deep crawl is the opposite of farm)
- Low-quality topic file missing → neutral `0.0`, flag `lq_topics_missing`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 10` pages per source AND LDA model trained on `≥ 1000` documents before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <10 MB (LDA model + topic-cache)  ·  RAM: <120 MB (LDA model loaded once per process)

## Scope boundary vs existing signals
FR-203 does NOT overlap with FR-198 keyword stuffing — that is per-page term anomaly. FR-203 is *source-level* topic + structural. It is also distinct from FR-054 boilerplate ratio and FR-203 farm score is multiplied at candidate level, not at page level.

## Test plan bullets
- unit tests: source with all-recipe-spam pages (high `lqts`), small organic source (low `pcf`)
- parity test: C++ vs Python combined score within `1e-4`
- regression test: legitimate large category (e.g. "Tech News") with non-low-quality topics gets `farm_score ≤ 0.20`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- LDA reload test: re-training LDA must not change `farm_score` ranking by more than `±10%` per source
- depth-norm sweep: `depth_norm ∈ {2, 4, 8}` produces monotone ordering on a fixed source
