# FR-172 — Normalized Query Commitment (NQC)

## Overview
NQC is a *post-retrieval* query-performance predictor that measures the *spread* of top-`k` retrieval scores. A confident query produces top-`k` scores that are tightly clustered above the corpus mean — high commitment. An ambiguous query produces top-`k` scores that fan out, suggesting the retrieval system is not strongly differentiating. Concretely it is the standard deviation of the top-`k` divided by the corpus baseline. Complements WIG (mean-vs-baseline) and Clarity (LM divergence) by being purely score-shape based.

## Academic source
Shtok, A., Kurland, O. and Carmel, D. "Predicting query performance by query-drift estimation." *Proceedings of the 18th ACM Conference on Information and Knowledge Management (CIKM '09)*, pp. 1881–1884, 2009. DOI: `10.1145/1645953.1646123`. Extended journal version: Shtok, A., Kurland, O., Carmel, D., Raiber, F. and Markovits, G. "Predicting query performance by query-drift estimation." *ACM TOIS* 30(2), 2012.

## Formula
From Shtok et al. (2009), Eq. 5 — NQC is the coefficient-of-variation of the top-`k` retrieval scores, with the corpus baseline `μ_C` (the score the corpus as a single document would receive) used as the normaliser:

```
NQC(Q) = σ_{topk} / |μ_C|

where
  μ_topk = (1/k) · Σ_{i=1..k} score(d_i, Q)
  σ_topk = √( (1/k) · Σ_{i=1..k} ( score(d_i, Q) − μ_topk )² )
  μ_C    = score(C, Q)   (whole-corpus document score)
```

Higher `NQC(Q)` ⇒ top-`k` scores spread sharply above the corpus mean ⇒ retrieval is confident and discriminative. The denominator `|μ_C|` removes per-corpus scale.

## Starting weight preset
```python
"nqc.enabled": "true",
"nqc.ranking_weight": "0.0",
"nqc.top_k": "100",
"nqc.scorer": "bm25",
"nqc.absolute_corpus_baseline": "true",
```

## C++ implementation
- File: `backend/extensions/nqc.cpp`
- Entry: `double nqc(const float* topk_scores, int k, double corpus_score)`
- Complexity: O(k) — single pass mean, second pass variance (or Welford's online update)
- Thread-safety: pure function; no shared state
- Builds via pybind11; Welford's algorithm to avoid catastrophic cancellation; double accumulator

## Python fallback
`backend/apps/pipeline/services/nqc.py::compute_nqc` using `np.std(scores, ddof=0) / abs(corpus_score)` with corpus baseline cached per scorer.

## Benchmark plan

| Size | Top-k | C++ target | Python target |
|---|---|---|---|
| Small | 10 | 0.005 ms | 0.05 ms |
| Medium | 100 | 0.03 ms | 0.4 ms |
| Large | 1,000 | 0.3 ms | 3.5 ms |

## Diagnostics
- NQC value rendered as "NQC: 0.42 (k=100)"
- Top-k score histogram in debug pane
- C++/Python badge
- Debug fields: `top_k`, `mean_topk`, `std_topk`, `corpus_baseline`, `scorer`

## Edge cases & neutral fallback
- `|μ_C| < ε` (corpus score near zero) ⇒ neutral 0.5, fallback flag set (avoid divide-by-zero)
- Top-`k` < 2 ⇒ standard deviation undefined ⇒ skip signal
- All scores identical ⇒ NQC = 0; reported as "no commitment" (degenerate-but-valid)
- Negative corpus baseline ⇒ use `|μ_C|` as normaliser; preserve sign of σ separately
- NaN / Inf scores ⇒ skip with state flag

## Minimum-data threshold
Need at least 5 retrieved documents and a non-zero corpus baseline before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0.05 MB (corpus baseline per scorer) · RAM: < 0.1 MB

## Scope boundary vs existing signals
Distinct from `fr170-query-clarity-score` (KL on LMs) and `fr171-weighted-information-gain` (mean-vs-baseline). NQC measures *spread* not *mean*. Both NQC and WIG can fire on the same query and report opposite verdicts (high mean, low variance ⇒ very confident; high variance, high mean ⇒ confident but wide). Not a per-document quality signal.

## Test plan bullets
- Unit: top-10 scores `[10, 10, 10, 10, 10]` returns NQC = 0
- Unit: top-10 scores spread `[5..15]` with `μ_C = 5` returns NQC ≈ 0.6
- Parity: C++ vs Python within 1e-6 on 500 queries
- Edge: corpus baseline 0 returns 0.5 with fallback
- Edge: top-k = 1 returns 0.5 with fallback (variance undefined)
- Integration: deterministic across runs at fixed top-k
- Regression: top-50 ranking unchanged when weight = 0.0
