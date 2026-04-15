# FR-171 — Weighted Information Gain (WIG)

## Overview
WIG is a *post-retrieval* query-performance predictor that compares the average retrieval score of the top-`k` documents to the score the corpus as a whole would receive against the same query. A high WIG means the top-`k` stand out sharply from the background — the query is well-served. A near-zero WIG means the top-`k` look just like the average document — the query is ambiguous. For internal linking, WIG flags host paragraphs whose retrieval into candidate destinations is confident vs. mush. Complements `fr170-query-clarity-score` (KL on LMs) and `fr172-normalized-query-commitment` (variance-based) by using raw scores rather than language models.

## Academic source
Zhou, Y. and Croft, W. B. "Query performance prediction in web search environments." *Proceedings of the 30th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '07)*, pp. 543–550, 2007. DOI: `10.1145/1277741.1277766`.

## Formula
From Zhou & Croft (2007), Eq. 4 — WIG averages the per-document log-likelihood gap between top-`k` retrieved documents and the entire collection treated as a single document, normalised by query length:

```
WIG(Q) = (1/k) · Σ_{i=1..k} ( log P(Q|d_i) − log P(Q|C) ) / |Q|

where
  log P(Q|d) = Σ_{w ∈ Q} log P(w|d)            (query likelihood model)
  log P(Q|C) = Σ_{w ∈ Q} log P(w|C)            (collection likelihood)
  |Q|        = number of query terms
  R_k(Q)     = top-k documents under the chosen retrieval scorer
```

For BM25 ranking the score itself substitutes for log-likelihood; in that case `WIG(Q) = (1/k)·Σ_{i=1..k} score(d_i, Q)/|Q|` minus the corpus baseline. Higher WIG ⇒ stronger retrieval signal.

## Starting weight preset
```python
"wig.enabled": "true",
"wig.ranking_weight": "0.0",
"wig.top_k": "5",
"wig.scorer": "bm25",
"wig.length_normalization": "true",
```

## C++ implementation
- File: `backend/extensions/wig.cpp`
- Entry: `double wig(const float* topk_scores, int k, double corpus_score, int query_len)`
- Complexity: O(k) summation; trivial after retrieval has been performed
- Thread-safety: pure function on input slice; no shared state
- Builds via pybind11; double accumulator for k-element reduction

## Python fallback
`backend/apps/pipeline/services/wig.py::compute_wig` using vectorised `np.mean` and the same scorer used for retrieval (BM25/QL) to ensure consistency.

## Benchmark plan

| Size | Top-k | C++ target | Python target |
|---|---|---|---|
| Small | 5 | 0.005 ms | 0.05 ms |
| Medium | 50 | 0.02 ms | 0.3 ms |
| Large | 500 | 0.15 ms | 2.5 ms |

## Diagnostics
- WIG value rendered as "WIG: +1.42 (top-5)"
- Per-document score deltas vs. corpus baseline
- C++/Python badge
- Debug fields: `top_k`, `scorer`, `query_len`, `corpus_log_likelihood`, `topk_mean_score`

## Edge cases & neutral fallback
- Empty top-k → neutral 0.5 with fallback flag
- `|Q| = 0` ⇒ skip signal, neutral 0.5
- Negative WIG (corpus outscores top-`k`) ⇒ clamp to 0 then map via sigmoid for ranking component
- Score scale mismatch (e.g., BM25 vs neural) ⇒ require all values from same scorer or fail with state flag
- Tie-broken top-`k` (multiple identical scores) ⇒ deterministic by document id

## Minimum-data threshold
Need at least 3 retrieved documents and `|Q| ≥ 1` before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0.05 MB (corpus baseline scalar per scorer) · RAM: < 0.1 MB

## Scope boundary vs existing signals
Distinct from `fr170-query-clarity-score` (KL on language models, not raw scores) and `fr172-normalized-query-commitment` (uses score variance, not score-vs-corpus delta). WIG operates only on retrieval scores; it does not need a vocabulary or LM. Does not duplicate `fr011-field-aware-relevance-scoring` which is a single-document scorer.

## Test plan bullets
- Unit: top-5 with mean score 10 vs corpus 5 returns WIG = 1.0 at |Q|=5
- Unit: top-5 identical to corpus returns WIG ≈ 0
- Parity: C++ vs Python within 1e-6 across 500 queries
- Edge: |Q|=0 returns 0.5 with fallback
- Edge: top-k empty returns 0.5 with fallback
- Integration: deterministic across runs at fixed top-k
- Regression: top-50 ranking unchanged when weight = 0.0
