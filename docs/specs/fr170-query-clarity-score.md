# FR-170 — Query Clarity Score

## Overview
Query Clarity is a *post-retrieval* query-performance predictor: how peaked is the language model induced by the top-`k` retrieved documents relative to the collection language model? A clear query produces a top-`k` LM that diverges sharply from background English; a vague query produces a top-`k` LM that looks just like the corpus. For an internal-linker, clarity tells the ranker whether the host paragraph is precise enough to suggest a confident link, or so generic that any insertion would be noisy. Complements `fr171-weighted-information-gain` (uses raw retrieval scores) and `fr173-simplified-clarity-score` (no retrieval needed).

## Academic source
Cronen-Townsend, S., Zhou, Y. and Croft, W. B. "Predicting query performance." *Proceedings of the 25th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '02)*, pp. 299–306, 2002. DOI: `10.1145/564376.564429`.

## Formula
From Cronen-Townsend et al. (2002), Eq. 1 — Clarity is the KL divergence of the query language model `P(w|Q)` from the collection language model `P(w|C)`, summed over the vocabulary `V`:

```
Clarity(Q) = Σ_{w ∈ V} P(w|Q) · log₂( P(w|Q) / P(w|C) )

where the query LM is mixed from the top-k retrieved documents:
  P(w|Q) = Σ_{d ∈ R_k(Q)} P(w|d) · P(d|Q)
  P(d|Q) ∝ P(Q|d) · P(d)                   (Bayes, uniform prior)
  P(w|d) = (1 − λ) · tf(w,d)/|d| + λ · P(w|C)   (Jelinek-Mercer smoothing)
```

Higher `Clarity(Q)` ⇒ retrieved set is topically focused; lower ⇒ retrieved set looks like random corpus. Typical values for English ad-hoc IR: 0.5 (vague) to 4.0 (highly specific).

## Starting weight preset
```python
"query_clarity.enabled": "true",
"query_clarity.ranking_weight": "0.0",
"query_clarity.top_k_for_qlm": "50",
"query_clarity.smoothing_lambda": "0.6",
"query_clarity.vocab_truncation_top_n": "500",
```

## C++ implementation
- File: `backend/extensions/query_clarity.cpp`
- Entry: `double query_clarity(const float* query_lm, const float* coll_lm, int vocab_size)`
- Complexity: O(|V|) for the KL sum; O(k · |d|) for the query LM mixture (computed once per query)
- Thread-safety: pure function; no shared state. SIMD log2 via vectorised polynomial approximation; double accumulator for KL reduction
- Builds via pybind11; precomputed log P(w|C) cached at startup

## Python fallback
`backend/apps/pipeline/services/query_clarity.py::compute_clarity` using NumPy `(p * np.log2(p / q)).sum()` with smoothing and zero-mass guards.

## Benchmark plan

| Size | Vocab | Top-k | C++ target | Python target |
|---|---|---|---|---|
| Small | 5,000 | 10 | 0.05 ms | 1.5 ms |
| Medium | 50,000 | 50 | 0.4 ms | 12 ms |
| Large | 500,000 | 200 | 4 ms | 110 ms |

## Diagnostics
- Clarity value rendered as "Clarity: 2.31 bits"
- Top-10 contributing terms (highest `P(w|Q) · log₂(P(w|Q)/P(w|C))`)
- C++/Python badge
- Debug fields: `top_k_used`, `smoothing_lambda`, `vocab_size`, `entropy_qlm`, `cross_entropy_qlm_clm`

## Edge cases & neutral fallback
- Empty query → neutral 0.5, fallback flag set
- Top-`k` retrieval returns 0 documents → neutral 0.5
- Any `P(w|Q) > 0` with `P(w|C) = 0` ⇒ clip via Laplace smoothing on collection LM
- Numerical underflow on `log₂(0)` ⇒ skipped (term contributes 0 by convention `0·log 0 = 0`)
- Vocabulary explosion ⇒ truncate to top-N query-mass terms (default 500)

## Minimum-data threshold
Need at least 10 retrieved documents and 50 query-LM probability mass terms before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0.3 MB (collection LM cache) · RAM: ~4 MB at |V|=500k (log-table + smoothed LM)

## Scope boundary vs existing signals
Distinct from `fr011-field-aware-relevance-scoring` (per-document field BM25), `fr173-simplified-clarity-score` (pre-retrieval, no top-k mixture), and `fr171-weighted-information-gain` (uses scores not LMs). Clarity is a query-side quality prior derived from retrieval shape, not a document quality signal.

## Test plan bullets
- Unit: query "the and a of" returns clarity ≈ 0 (matches collection LM)
- Unit: query "fluorinated graphene" returns clarity > 3.0 on a general-news corpus
- Parity: C++ vs Python on 500 queries within 1e-4 bits
- Edge: empty top-k returns 0.5 with fallback flag
- Edge: vocabulary of size 1 returns 0.0 (degenerate)
- Integration: deterministic across runs at fixed `top_k` and `lambda`
- Regression: top-50 ranking unchanged when weight = 0.0
