# FR-112 - MinSpan Proximity Score

## Overview
The minimum span of a query in a document is the shortest interval that contains at least one occurrence of every query term. A short min-span means all query terms cluster together — strong evidence the document is on-topic. The MinSpan score is `1 / (minSpan − |Q| + 1)` so a perfect contiguous match scores 1.0 and longer spans decay smoothly. It is the most intuitive proximity feature and the cheapest to compute. Complements FR-111 because MinSpan looks at the whole-query span while BM25TP only sums per-pair distances.

## Academic source
**Tao, Tao and Zhai, ChengXiang (2007).** "An Exploration of Proximity Measures in Information Retrieval." *Proceedings of the 30th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2007)*, pp. 295-302. DOI: `10.1145/1277741.1277794`. (MinSpan is one of five proximity measures evaluated; the paper concludes MinDist is the strongest.)

## Formula
From Tao & Zhai (2007), §3.2 (MinDist / MinSpan):

```
minSpan(Q, D) = min_{interval I ⊆ [1, |D|]}  |I|
                  subject to:  ∀ q ∈ Q ∩ D,  ∃ position p ∈ I  with token at p = q

minSpan_score(Q, D) = α / ( α + log( 1 + minSpan(Q, D) − |Q ∩ D| + 1 ) )

final(Q, D) = base(Q, D) · minSpan_score(Q, D)        (if used as a multiplier)
```

Where:
- `Q ∩ D` = query terms present in `D`
- `α > 0` = decay constant (default 0.3 per paper §4.1 grid search)
- `base(Q, D)` = any base scorer (BM25, LM); when used standalone the multiplier is omitted and `minSpan_score` is the signal directly
- The `−|Q∩D| + 1` shift makes a perfect contiguous match map to `log(1) = 0` so `minSpan_score = 1.0`

## Starting weight preset
```python
"minspan.enabled": "true",
"minspan.ranking_weight": "0.0",
"minspan.alpha": "0.3",
"minspan.usage": "standalone",   # "standalone" returns minSpan_score; "multiplier" multiplies base
```

## C++ implementation
- File: `backend/extensions/minspan.cpp`
- Entry: `double minspan_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, double alpha);`
- Complexity: `O(|D| · |Q|)` worst case using a sliding-window two-pointer over merged positional postings; for the typical anchor-text query (`|Q| ≤ 5`) this is `O(|D|)`
- Thread-safety: pure function
- SIMD: position-merge already vectorisable
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/minspan.py::score_minspan(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.1 ms | < 1 ms |
| 100 | < 0.5 ms | < 5 ms |
| 500 | < 2 ms | < 25 ms |

## Diagnostics
- `minSpan` integer (the actual span length found)
- Position interval `[p_start, p_end]` of the winning span
- C++ vs Python badge
- `α` actually applied
- `|Q ∩ D|` versus `|Q|` so operator can see partial-coverage cases

## Edge cases & neutral fallback
- `|Q| = 1` → minSpan = 1 (any single occurrence); score = `α / (α + log(1)) = 1.0`
- `Q ∩ D = ∅` → no span exists; score = 0.0, flag `no_overlap`
- `|Q ∩ D| < |Q|` → score computed only over present terms; flag `partial_coverage`
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → neutral 0.5, flag `no_positions`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Document with ≥ 1 token having positional data; corpus stats not required (MinSpan is corpus-free).

## Budget
Disk: <1 MB  ·  RAM: <10 MB (positional postings only)

## Scope boundary vs existing signals
FR-112 does NOT duplicate FR-111 BM25TP because BM25TP sums per-pair `1/d²` while MinSpan looks at the smallest interval covering all query terms; the two give different rankings for queries with repeated terms or asymmetric pair distances. It does not duplicate FR-108 SDM because MinSpan is a single number per document, not an MRF score.

## Test plan bullets
- unit tests: `|Q| = 1`, exact contiguous match, partial coverage, all terms far apart
- parity test: C++ vs Python within `1e-4`
- correctness test: brute-force minSpan on small docs matches sliding-window result
- monotonicity: shorter span strictly raises score
- no-crash test on adversarial input (very long doc, all positions identical)
- integration test: ranking unchanged when `ranking_weight = 0.0`
