# FR-175 — Query Feedback

## Overview
Query Feedback is a *post-retrieval* query-performance predictor that asks: if I generate a paraphrase `Q'` from the top-`k` retrieved documents and re-retrieve, how much does the new top-`k'` set overlap with the original top-`k`? High overlap means the retrieval is robust to query reformulation — the system has zeroed in on a stable topic. Low overlap means the original retrieval was sensitive to the exact query phrasing — fragile result. For an internal-linker, query feedback flags brittle suggestions whose ranking would flip under small wording changes. Complements WIG (mean-vs-baseline) and Clarity (LM divergence) with a *stability* axis.

## Academic source
Zhou, Y. and Croft, W. B. "Ranking robustness: a novel framework to predict query performance." *Proceedings of the 15th ACM International Conference on Information and Knowledge Management (CIKM '06)*, pp. 567–574, 2006. DOI: `10.1145/1183614.1183696`. Refined and renamed "Query Feedback" in: Zhou, Y. and Croft, W. B. SIGIR 2007. DOI: `10.1145/1148170.1148261`.

## Formula
From Zhou & Croft (2006), Algorithm 1 — Query Feedback is the size of the intersection between the original top-`k` and the top-`k'` retrieved by a paraphrased query, divided by `k`:

```
QF(Q) = | R_k(Q) ∩ R_k(Q') | / k

where
  R_k(Q)  = top-k documents retrieved for the original query Q
  Q'      = paraphrase of Q sampled from the top-k LM
  R_k(Q') = top-k documents retrieved for Q'
```

Paraphrase generation in the original paper:

```
1. Build query LM P(w|Q) = Σ_{d ∈ R_k(Q)} P(w|d) · P(d|Q)
2. Sample |Q'| terms from P(w|Q) (with multinomial sampling, size |Q'|=|Q|+5)
3. Issue Q' against the same index
```

Higher QF ⇒ retrieval is robust to query rewording ⇒ confident query.

## Starting weight preset
```python
"query_feedback.enabled": "true",
"query_feedback.ranking_weight": "0.0",
"query_feedback.top_k": "50",
"query_feedback.paraphrase_extra_terms": "5",
"query_feedback.paraphrase_seed": "42",
```

## C++ implementation
- File: `backend/extensions/query_feedback.cpp`
- Entry: `double query_feedback(const int* topk_docs, int k, const int* topk_doc_paraphrase, int k2)`
- Complexity: O(k log k) for sorted-merge intersection (or O(k) with hash set); paraphrase retrieval cost dominates
- Thread-safety: pure function; deterministic given seed
- Builds via pybind11; xorshift RNG for paraphrase sampling

## Python fallback
`backend/apps/pipeline/services/query_feedback.py::compute_qf` using `set(R_k(Q)).intersection(R_k(Q_prime))` and the project's existing retriever.

## Benchmark plan

| Size | Top-k | C++ target | Python target |
|---|---|---|---|
| Small | 10 | 0.005 ms | 0.05 ms |
| Medium | 50 | 0.02 ms | 0.2 ms |
| Large | 500 | 0.2 ms | 2.0 ms |

## Diagnostics
- QF value rendered as "Query Feedback: 0.74 (37/50 docs overlap)"
- Paraphrase shown to operator (top weighted terms)
- C++/Python badge
- Debug fields: `top_k`, `paraphrase_terms`, `paraphrase_seed`, `intersection_size`

## Edge cases & neutral fallback
- Empty top-k ⇒ neutral 0.5 with fallback flag
- Paraphrase identical to query (degenerate sample) ⇒ QF = 1.0; reported as "trivial"
- Retrieval cost: paraphrase requires a second retrieval pass — gate behind ranking_weight > 0 to avoid doubling cost
- Random seed must be deterministic across runs for reproducibility
- `|Q'| = 0` (sampler produced empty query) ⇒ resample up to 3 times, then fallback

## Minimum-data threshold
Need at least 5 retrieved documents in original top-k before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0 (no model) · RAM: ~10 KB (paraphrase term buffer + intersection set)

## Scope boundary vs existing signals
Distinct from WIG (mean-of-scores) and NQC (variance-of-scores). QF measures *retrieval stability* under input perturbation; it is the only predictor in the family that requires a second retrieval pass. Not duplicated by FR-014 (near-duplicate clustering) which is destination-side, not query-side.

## Test plan bullets
- Unit: identical Q and Q' ⇒ QF = 1.0
- Unit: Q' that retrieves fully disjoint set ⇒ QF = 0.0
- Parity: C++ vs Python within ≤2 docs on 500 queries (sampling variance permitted at fixed seed)
- Edge: top-k = 0 returns 0.5 with fallback
- Edge: paraphrase sampler fails 3x returns 0.5 with fallback
- Integration: deterministic across runs at fixed seed
- Regression: top-50 ranking unchanged when weight = 0.0
