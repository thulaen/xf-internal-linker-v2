# FR-177 — Sum of Collection Query (SCQ)

## Overview
SCQ is a *pre-retrieval* query-performance predictor based on TF-IDF magnitude. It treats the *collection itself* as a single document and computes the sum of `(1 + log tf(w,C)) · idf(w)` over query terms. A query whose terms have both high collection frequency AND high IDF (rare-but-present in many fields) tends to retrieve well; a query whose terms are absent or only-ever-stopword tends to retrieve poorly. Complements `fr173-simplified-clarity-score`, `fr174-query-scope`, and `fr176-avg-ictf-preretrieval-predictor` by combining TF and IDF rather than each alone. The original paper found SCQ to be one of the strongest pre-retrieval predictors on TREC ad-hoc collections.

## Academic source
Zhao, Y., Scholer, F. and Tsegay, Y. "Effective pre-retrieval query performance prediction using similarity and variability evidence." *Advances in Information Retrieval (ECIR 2008), Lecture Notes in Computer Science vol 4956*, Springer, pp. 52–64, 2008. DOI: `10.1007/978-3-540-78646-7_8`. Companion variant in same paper introduces SumSCQ, MaxSCQ, AvgSCQ.

## Formula
From Zhao, Scholer & Tsegay (2008), Eq. 3 — SCQ for a query `Q` against collection `C`:

```
SCQ(Q, C) = Σ_{w ∈ Q} ( 1 + log tf(w, C) ) · idf(w)

where
  tf(w, C) = total occurrences of term w in collection C
  idf(w)   = log( N / df(w) )
  N        = number of documents in C
  df(w)    = number of documents containing w
```

Variants (also in the paper):

```
AvgSCQ(Q, C) = SCQ(Q, C) / |Q|       (per-term mean)
MaxSCQ(Q, C) = max_{w ∈ Q} (1 + log tf(w, C)) · idf(w)   (single best term)
```

The default in this spec is the paper's *summed* form; the variants are exposed via settings.

## Starting weight preset
```python
"scq.enabled": "true",
"scq.ranking_weight": "0.0",
"scq.variant": "sum",
"scq.distinct_terms_only": "true",
"scq.smoothing_epsilon": "1e-6",
```

## C++ implementation
- File: `backend/extensions/scq.cpp`
- Entry: `double scq(const int* query_term_ids, int q_len, const float* log_tf_c, const float* idf_w, int variant)`
- Complexity: O(|Q|) — single pass with two precomputed lookup tables
- Thread-safety: pure function; lookups are read-only
- Builds via pybind11; `variant` enum: 0=sum, 1=avg, 2=max

## Python fallback
`backend/apps/pipeline/services/scq.py::compute_scq` using vectorised NumPy: `np.sum((1 + log_tf[ids]) * idf[ids])`.

## Benchmark plan

| Size | |Q| | C++ target | Python target |
|---|---|---|---|
| Small | 5 | 0.001 ms | 0.02 ms |
| Medium | 20 | 0.005 ms | 0.06 ms |
| Large | 200 | 0.04 ms | 0.5 ms |

## Diagnostics
- SCQ value rendered as "SCQ: 47.3 (sum)" or "SCQ: 9.5 (avg)"
- Per-term `(1 + log tf) · idf` breakdown
- C++/Python badge
- Debug fields: `variant`, `distinct_query_terms`, `mean_term_score`, `max_term_score`, `unseen_terms_count`

## Edge cases & neutral fallback
- Empty query ⇒ neutral 0.5 with fallback flag
- OOV term ⇒ `log tf(w, C)` undefined; apply Laplace add-ε smoothing (`tf(w,C) + ε`) and skip if ε contribution dominates
- `df(w) = N` (term in every doc) ⇒ `idf(w) = 0` ⇒ that term contributes 0 to SCQ
- Variant must be one of {sum, avg, max}; reject unknown values
- `|Q| = 0` for AvgSCQ ⇒ neutral 0.5

## Minimum-data threshold
Need at least 1 in-vocabulary query term and a corpus of `N ≥ 100` documents before signal contributes.

## Budget
Disk: ~8 MB combined `log_tf` + `idf` for 1M-term vocab · RAM: same arrays (mmap'd)

## Scope boundary vs existing signals
Distinct from `fr173-simplified-clarity-score` (KL on uniform query LM), `fr174-query-scope` (doc-frequency based), and `fr176-avg-ictf-preretrieval-predictor` (collection-frequency based, no IDF). SCQ uniquely combines `tf(w,C)` and `idf(w)`. Pre-retrieval only.

## Test plan bullets
- Unit: query of one rare-but-not-tiny term returns SCQ in mid range
- Unit: query of common stopwords returns SCQ near 0 (idf=0)
- Variants: SumSCQ ≥ MaxSCQ ≥ AvgSCQ for any |Q| > 1
- Parity: C++ vs Python within 1e-6 on 1,000 queries × 3 variants
- Edge: OOV-only query returns 0.5 with fallback
- Integration: deterministic across runs given fixed corpus
- Regression: top-50 ranking unchanged when weight = 0.0
