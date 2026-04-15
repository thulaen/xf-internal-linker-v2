# FR-099 - BM25+ Lower-Bound Term-Frequency Normalization

## Overview
Standard BM25 systematically under-weights very long documents because the term-frequency component decays toward zero as `|D|/avgdl` grows. Long forum threads (which a XenForo/WordPress corpus has many of) get penalised even when they unambiguously contain a query term. BM25+ adds a constant lower-bound `δ` so any present term keeps a minimum credit. Complements existing FR-011 BM25 because it preserves the same calibration knobs (`k₁`, `b`) while fixing the long-document tail.

## Academic source
**Lv, Yuanhua and Zhai, ChengXiang (2011).** "Lower-Bounding Term Frequency Normalization." *Proceedings of the 20th ACM International Conference on Information and Knowledge Management (CIKM 2011)*, pp. 7-16. DOI: `10.1145/2063576.2063584`.

## Formula
From Lv & Zhai (2011), Eq. 7:

```
BM25+(Q, D) = Σ_{q ∈ Q}  IDF(q) · [ (tf(q,D) · (k₁+1)) / (tf(q,D) + k₁·(1 − b + b·|D|/avgdl)) + δ ]

IDF(q) = log( (N − df(q) + 0.5) / (df(q) + 0.5) + 1 )
```

Where:
- `tf(q,D)` = term frequency of `q` in document `D`
- `df(q)` = number of documents containing `q`
- `N` = total documents in the corpus
- `|D|` = document length in tokens, `avgdl` = mean document length
- `k₁ ∈ [1.2, 2.0]` = term saturation (default 1.2 per paper Table 2)
- `b ∈ [0.6, 0.9]` = length normalisation (default 0.75 per paper Table 2)
- `δ ≥ 0` = lower-bound shift (default 1.0 per paper Table 2)

## Starting weight preset
```python
"bm25_plus.enabled": "true",
"bm25_plus.ranking_weight": "0.0",   # inert until implementation
"bm25_plus.k1": "1.2",
"bm25_plus.b": "0.75",
"bm25_plus.delta": "1.0",
```

## C++ implementation
- File: `backend/extensions/bm25plus.cpp`
- Entry: `double bm25_plus_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double k1, double b, double delta);`
- Complexity: `O(|Q|)` per (query, doc) pair — reuses posting-list lookups in `scoring.cpp`
- Thread-safety: pure function, no shared state; safe under OpenMP
- SIMD: `#pragma omp simd reduction(+:score)` over the query-term loop
- Builds against pybind11 like existing extensions

## Python fallback
`backend/apps/pipeline/services/bm25plus.py::score_bm25_plus(...)` — used when the C++ extension is unavailable (CI without compilation, diagnostics replay).

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.05 ms | < 0.5 ms |
| 100 | < 0.2 ms | < 5 ms |
| 500 | < 1 ms | < 25 ms |

## Diagnostics
- Raw BM25+ score in suggestion detail UI
- C++ vs Python badge
- Was `δ` floor active for this document (yes/no)
- IDF sum and length-normalisation factor exposed for inspection

## Edge cases & neutral fallback
- Zero query-doc term overlap → score = 0.0, no flag
- Empty document `|D| = 0` → return 0.0, flag `empty_doc`
- Missing `avgdl` (fresh corpus) → neutral 0.5, flag `no_corpus_stats`
- Extreme `tf` (spam bomb) → clamped at `max_tf = 10000`, flag `tf_clamped`
- NaN / Inf → clamped to 0.0, flag `nan_clamped`

## Minimum-data threshold
≥ 10 documents in the corpus before `avgdl` is meaningful; below this the signal returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-099 does NOT duplicate FR-011 BM25 because FR-099 adds a lower-bound floor that FR-011 lacks; the two signals can be wired in parallel and a tuner can select between them. It complements FR-018 auto-tuner by giving it an extra uncorrelated term-weight feature with a different long-document profile.

## Test plan bullets
- unit tests for empty / zero-overlap / single-term / large `|D|` inputs
- parity test: C++ vs Python within `1e-4` over 1000 random queries
- no-crash test on adversarial input (huge `tf`, zero `df`, NaN length)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: BM25+ ≥ BM25 for any document where δ-term is active
