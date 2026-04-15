# FR-173 — Simplified Clarity Score (SCS)

## Overview
Simplified Clarity is a *pre-retrieval* version of FR-170 Clarity: it estimates query specificity *without running retrieval first*. Instead of mixing a query LM from top-`k` documents, it uses a uniform LM over the query terms themselves and computes KL divergence against the collection LM. Cheap, deterministic, and independent of retrieval quality — useful as a feature in linear blends and as a sanity check on full Clarity. Complements `fr174-query-scope` (corpus coverage of query terms) by being information-theoretic rather than coverage-based.

## Academic source
He, B. and Ounis, I. "Inferring query performance using pre-retrieval predictors." *String Processing and Information Retrieval (SPIRE 2004), Lecture Notes in Computer Science vol 3246*, Springer, pp. 43–54, 2004. DOI: `10.1007/978-3-540-30213-1_5`. Companion ECIR paper: He & Ounis (2004) DOI: `10.1007/978-3-540-24752-4_4`.

## Formula
From He & Ounis (2004), Section 3 — SCS is the KL divergence of a uniform query LM `P_Q(w) = 1/|Q|` for `w ∈ Q` from the collection LM `P_C(w)`:

```
SCS(Q) = Σ_{w ∈ Q} P_Q(w) · log₂( P_Q(w) / P_C(w) )

where
  P_Q(w) = 1 / |Q|                         (uniform over distinct query terms)
  P_C(w) = tf(w, C) / |C|                  (collection unigram LM)
  |Q|    = number of distinct query terms
```

Equivalently:

```
SCS(Q) = log₂(1/|Q|) − (1/|Q|) · Σ_{w ∈ Q} log₂ P_C(w)
       = AvgICTF(Q) − log₂(|Q|)            (link to FR-176)
```

Higher SCS ⇒ query terms are individually rare in the corpus ⇒ specific query.

## Starting weight preset
```python
"scs.enabled": "true",
"scs.ranking_weight": "0.0",
"scs.distinct_terms_only": "true",
"scs.smoothing_epsilon": "1e-6",
```

## C++ implementation
- File: `backend/extensions/scs.cpp`
- Entry: `double scs(const int* query_term_ids, int query_len, const float* collection_log_probs)`
- Complexity: O(|Q|) — single pass; collection log-probs precomputed at index time
- Thread-safety: pure function; collection LM is read-only after build
- Builds via pybind11; double accumulator for log sum

## Python fallback
`backend/apps/pipeline/services/scs.py::compute_scs` using NumPy gather on a precomputed `log_p_collection[term_id]` array.

## Benchmark plan

| Size | Query terms | C++ target | Python target |
|---|---|---|---|
| Small | 5 | 0.001 ms | 0.02 ms |
| Medium | 20 | 0.005 ms | 0.08 ms |
| Large | 200 | 0.05 ms | 0.7 ms |

## Diagnostics
- SCS value rendered as "SCS: 8.4 bits"
- Per-term `log P_C(w)` contributions in debug pane
- C++/Python badge
- Debug fields: `distinct_query_terms`, `mean_log_p_c`, `unseen_terms_count`, `smoothing_epsilon`

## Edge cases & neutral fallback
- Empty query → neutral 0.5 with fallback flag
- Out-of-vocabulary term ⇒ apply Laplace add-ε smoothing (default ε = 1e-6) to keep `P_C(w) > 0`
- Single query term ⇒ SCS reduces to `−log₂ P_C(w)` (still meaningful)
- `|Q|` should count distinct terms; repeated terms collapse to one (per the paper)
- Stopword-only query ⇒ SCS very low; reported as "low specificity"

## Minimum-data threshold
Need at least 1 in-vocabulary query term; if every term OOV, fall back to neutral 0.5.

## Budget
Disk: ~4 MB precomputed `log_p_collection` for 1M-term vocab · RAM: same array, mmap'd

## Scope boundary vs existing signals
Distinct from `fr170-query-clarity-score` (post-retrieval, uses top-k mixture) and `fr176-avg-ictf-preretrieval-predictor` (no `log₂(|Q|)` correction). SCS is essentially a length-corrected AvgICTF. Pre-retrieval only: never reads candidate documents.

## Test plan bullets
- Unit: query of one ultra-rare term returns SCS ≥ 15 bits
- Unit: query of common stopwords returns SCS near 0
- Identity: SCS(Q) == AvgICTF(Q) − log₂(|Q|) within 1e-6
- Parity: C++ vs Python within 1e-6 on 1,000 queries
- Edge: OOV-only query returns 0.5 with fallback
- Integration: deterministic across runs given fixed corpus LM
- Regression: top-50 ranking unchanged when weight = 0.0
