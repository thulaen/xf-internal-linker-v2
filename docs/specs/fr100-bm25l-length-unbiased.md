# FR-100 - BM25L Length-Unbiased Term-Frequency Normalization

## Overview
BM25 has a known bias: medium-long documents are over-penalised by the `b·|D|/avgdl` term even when their length matches the topic naturally. BM25L re-centres the length factor so the penalty curve is symmetric around `avgdl`. Forum threads vary wildly in length (one-line replies vs 50-post deep dives), so a length-unbiased variant is a better neighbour to FR-099 than yet another tuned BM25. Complements FR-099 because the two papers fix different failure modes of the same base scorer.

## Academic source
**Lv, Yuanhua and Zhai, ChengXiang (2011).** "When Documents Are Very Long, BM25 Fails!" *Proceedings of the 34th International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2011)*, pp. 1103-1104. DOI: `10.1145/2009916.2010070`. (Companion to the ECIR 2011 BM25L paper "Adaptive Term Frequency Normalization for BM25", DOI: `10.1145/2063576.2063590`.)

## Formula
From Lv & Zhai (2011), the BM25L term-frequency adjustment, Eq. 4:

```
c'(q,D) = tf(q,D) / (1 − b + b·|D|/avgdl)

BM25L(Q,D) = Σ_{q ∈ Q}  IDF(q) · ( (k₁+1) · (c'(q,D) + δ) ) / (k₁ + c'(q,D) + δ)
```

Where:
- `tf(q,D)`, `|D|`, `avgdl`, `IDF(q)` as in BM25
- `c'(q,D)` = length-adjusted term frequency
- `k₁ ∈ [1.2, 2.0]` = saturation (default 1.2)
- `b ∈ [0.6, 0.9]` = length normalisation (default 0.75)
- `δ ≥ 0` = additive shift on the adjusted tf (default 0.5 per paper Table 2 — note: smaller than BM25+'s δ because it is added inside the saturation curve, not outside)

## Starting weight preset
```python
"bm25l.enabled": "true",
"bm25l.ranking_weight": "0.0",
"bm25l.k1": "1.2",
"bm25l.b": "0.75",
"bm25l.delta": "0.5",
```

## C++ implementation
- File: `backend/extensions/bm25l.cpp`
- Entry: `double bm25l_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double k1, double b, double delta);`
- Complexity: `O(|Q|)` per (query, doc) — same posting-list path as FR-099
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/bm25l.py::score_bm25l(...)` — only when extension unavailable.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.05 ms | < 0.5 ms |
| 100 | < 0.2 ms | < 5 ms |
| 500 | < 1 ms | < 25 ms |

## Diagnostics
- Raw BM25L score
- C++ vs Python badge
- Length-adjusted tf (`c'`) per query term
- Whether `δ` shift dominated for any query term

## Edge cases & neutral fallback
- Zero overlap → score = 0.0
- `|D| = 0` → 0.0, flag `empty_doc`
- Missing `avgdl` → neutral 0.5, flag `no_corpus_stats`
- `tf` clamped at `max_tf = 10000`, flag `tf_clamped`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 10 documents before `avgdl` is trusted; below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-100 does NOT duplicate FR-099 BM25+ because the δ shift is applied inside the saturation curve, not outside it; the two produce different rankings on the same input. It complements FR-011 by giving the auto-tuner a length-corrected variant that pairs well with mid-length forum threads.

## Test plan bullets
- unit tests: empty / single-term / very-long / very-short documents
- parity test: C++ vs Python within `1e-4`
- no-crash test on adversarial input
- integration test: ranking unchanged when `ranking_weight = 0.0`
- length-bias test: BM25L should rank a 2×avgdl document strictly above plain BM25 for the same `tf` distribution
