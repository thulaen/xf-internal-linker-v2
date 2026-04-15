# FR-176 — Average Inverse Collection Term Frequency (AvgICTF)

## Overview
AvgICTF is a *pre-retrieval* query-performance predictor: the average inverse collection-term-frequency of query terms. Conceptually it asks "are these query terms rare in the corpus?" A query of rare terms scores high (likely specific); a query of common stopwords scores low. AvgICTF is the simplest, fastest pre-retrieval predictor and is closely related to SCS (FR-173) and IDF. For internal linking, AvgICTF gives the ranker an O(|Q|) specificity prior with no retrieval cost. Complements `fr173-simplified-clarity-score` (which subtracts `log₂|Q|`), `fr174-query-scope` (document-frequency based), and `fr177-scq-preretrieval-predictor` (TF-IDF magnitude).

## Academic source
He, B. and Ounis, I. "Inferring query performance using pre-retrieval predictors." *Proceedings of the 27th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '04) — Workshop on Predicting Query Difficulty*, 2004. Also published as: He & Ounis (2006), "Query performance prediction." *Information Systems* 31(7), pp. 585–594. DOI: `10.1016/j.is.2005.11.003`.

## Formula
From He & Ounis (2004), Section 2.2 — AvgICTF averages `log( |C| / tf(w, C) )` over the distinct query terms `w ∈ Q`:

```
AvgICTF(Q) = (1/|Q|) · Σ_{w ∈ Q} log( |C| / tf(w, C) )

where
  tf(w, C) = total occurrences of term w across the entire collection
  |C|      = total number of tokens in the collection
  |Q|      = number of distinct query terms
```

Equivalence to SCS (FR-173):

```
SCS(Q) = AvgICTF(Q) − log₂(|Q|)
```

Higher AvgICTF ⇒ rarer query terms ⇒ more specific query. Typical value range: 5–20 bits.

## Starting weight preset
```python
"avgictf.enabled": "true",
"avgictf.ranking_weight": "0.0",
"avgictf.distinct_terms_only": "true",
"avgictf.smoothing_epsilon": "1e-6",
```

## C++ implementation
- File: `backend/extensions/avgictf.cpp`
- Entry: `double avgictf(const int* query_term_ids, int q_len, const float* log_inv_ctf)`
- Complexity: O(|Q|) — single pass over query term ids
- Thread-safety: pure function; precomputed `log_inv_ctf[term_id]` is read-only
- Builds via pybind11; double accumulator

## Python fallback
`backend/apps/pipeline/services/avgictf.py::compute_avgictf` using `np.mean(log_inv_ctf[term_ids])` with OOV smoothing.

## Benchmark plan

| Size | |Q| | C++ target | Python target |
|---|---|---|---|
| Small | 5 | 0.001 ms | 0.02 ms |
| Medium | 20 | 0.005 ms | 0.06 ms |
| Large | 200 | 0.04 ms | 0.5 ms |

## Diagnostics
- AvgICTF value rendered as "AvgICTF: 11.2 bits"
- Per-term `log(|C|/tf(w,C))` contributions
- C++/Python badge
- Debug fields: `distinct_query_terms`, `mean_log_inv_ctf`, `unseen_terms_count`

## Edge cases & neutral fallback
- Empty query ⇒ neutral 0.5 with fallback flag
- OOV term ⇒ apply Laplace add-ε smoothing (`tf(w,C) + ε`) to avoid `log(|C|/0)`
- Single query term ⇒ AvgICTF = `log(|C|/tf(w,C))` (still valid)
- Query of all stopwords ⇒ AvgICTF very low (correctly flags vagueness)
- Distinct-terms toggle: repeated terms count once per the paper

## Minimum-data threshold
Need at least 1 in-vocabulary query term; if every term OOV, fall back to neutral 0.5.

## Budget
Disk: ~4 MB precomputed `log_inv_ctf` for 1M-term vocab · RAM: same array (mmap'd)

## Scope boundary vs existing signals
Distinct from `fr173-simplified-clarity-score` (subtracts `log₂|Q|`) and `fr174-query-scope` (document-frequency based). AvgICTF is the simplest specificity prior in the family. Pre-retrieval only. Does not overlap with `fr011-field-aware-relevance-scoring` (per-document scorer).

## Test plan bullets
- Unit: query of one ultra-rare term returns AvgICTF ≥ 15 bits
- Unit: query of common stopwords returns AvgICTF near 0
- Identity: SCS(Q) = AvgICTF(Q) − log₂(|Q|) within 1e-6
- Parity: C++ vs Python within 1e-6 on 1,000 queries
- Edge: OOV-only query returns 0.5 with fallback
- Integration: deterministic across runs given fixed corpus
- Regression: top-50 ranking unchanged when weight = 0.0
