# FR-111 - BM25TP (BM25 + Term Proximity)

## Overview
SDM (FR-108) and FDM (FR-110) deliver the strongest term-dependence rankings but pay an `O(|Q|·|D|)` proximity scan per (query, doc). BM25TP is the lightweight proximity add-on: take a standard BM25 score and add a per-document proximity boost that grows with the inverse-square of the in-document distance between query-term occurrences. One pass over positions is enough. Complements FR-099 / FR-100 / FR-011 because BM25TP is the cheapest way to inject a proximity bonus into any BM25-family scorer.

## Academic source
**Rasolofo, Yves and Savoy, Jacques (2003).** "Term Proximity Scoring for Keyword-Based Retrieval Systems." *Advances in Information Retrieval (ECIR 2003)*, LNCS 2633, pp. 207-218. DOI: `10.1007/3-540-36618-0_15`.

## Formula
From Rasolofo & Savoy (2003), Eqs. 1-3:

```
acc(q_i, q_j, D) = Σ_{(p_i, p_j) ∈ pairs}  1 / (|p_i − p_j|)²
                   for all positions p_i of q_i and p_j of q_j in D, with |p_i − p_j| < W

tpi(q_i, D) = Σ_{q_j ≠ q_i in Q ∩ D}  acc(q_i, q_j, D)

BM25TP(Q, D) = BM25(Q, D)
             + Σ_{q_i ∈ Q ∩ D}  IDF(q_i) · ( ((k₁ + 1) · tpi(q_i, D)) / (K + tpi(q_i, D)) )

K = k₁ · (1 − b + b · |D| / avgdl)
```

Where:
- `BM25(Q, D)` = standard BM25 score (use FR-011 result directly)
- `IDF(q_i)`, `k₁`, `b`, `|D|`, `avgdl` as in BM25
- `W` = proximity window in tokens (default 5 per paper §3, "minimal context")
- `tpi(q_i, D)` = "term-pair information" for term `q_i`
- The proximity-saturation form `((k+1)·tpi)/(K+tpi)` mirrors BM25's tf-saturation so the bonus is bounded

## Starting weight preset
```python
"bm25tp.enabled": "true",
"bm25tp.ranking_weight": "0.0",
"bm25tp.k1": "1.2",
"bm25tp.b": "0.75",
"bm25tp.window": "5",
```

## C++ implementation
- File: `backend/extensions/bm25tp.cpp`
- Entry: `double bm25tp_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, const CorpusStats& corp, double k1, double b, int window);`
- Complexity: `O(|D|)` per (query, doc) — single pass over positions with an active query-term map; `tpi` accumulates as the scan proceeds
- Thread-safety: pure function
- SIMD: position-merge loop vectorised; `1/d²` lookup table for `d ∈ [1, W]`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/bm25tp.py::score_bm25tp(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.2 ms | < 2 ms |
| 100 | < 1 ms | < 10 ms |
| 500 | < 5 ms | < 50 ms |

## Diagnostics
- Base BM25 score and proximity-bonus separately
- C++ vs Python badge
- `tpi(q_i, D)` per query term
- Effective `W` actually used

## Edge cases & neutral fallback
- `|Q| = 1` → no pairs, proximity bonus = 0; reduces to BM25 exactly
- `Q ∩ D = ∅` → 0.0
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → reduces to BM25 only, flag `no_positions`
- All pair distances ≥ `W` → proximity bonus = 0, flag `no_close_pairs`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Corpus ≥ 10 docs (BM25 base requirement); below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <10 MB (positional postings)

## Scope boundary vs existing signals
FR-111 does NOT duplicate FR-108 SDM because BM25TP wraps BM25 and adds a single-pass proximity bonus rather than building a 3-component MRF. It complements FR-099 / FR-100 / FR-011 by being the cheapest way to inject term-pair locality into any BM25 variant; the auto-tuner can choose which BM25 base to wrap.

## Test plan bullets
- unit tests: `|Q| = 1` (no bonus), `|Q| = 2`, repeated terms, all terms at same position
- parity test: C++ vs Python within `1e-4`
- limit check: `W = 1` matches exact-adjacent only
- monotonicity: closer pairs strictly increase the bonus (`1/d²` is decreasing)
- no-crash test on adversarial input (`|D|` huge, `W = 0`)
- integration test: ranking unchanged when `ranking_weight = 0.0`
