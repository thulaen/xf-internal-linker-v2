# FR-102 - DFR InL2 (Inverse-Document-Frequency Laplacian)

## Overview
InL2 is the I(n)·L·H2 cell of the DFR matrix: an inverse-document-frequency basic model (`I(n)`) combined with the Laplace after-effect normalisation (`L`) and the same H2 length normalisation as PL2. It is especially strong on rare query terms, exactly the regime where forum-specific jargon and proper nouns live. Complements FR-010 rare-term propagation because FR-010 expands which posts inherit a rare term while FR-102 quantifies how rare a term's appearance is at scoring time.

## Academic source
**Amati, Gianni (2003).** "Probability Models for Information Retrieval Based on Divergence from Randomness." *PhD Thesis, University of Glasgow*. (Plus the same TOIS 2002 framework paper, DOI: `10.1145/582415.582416`.) Glasgow EThOS handle: `https://theses.gla.ac.uk/1570/`.

## Formula
From Amati (2003), Chapter 3, with the I(n) basic model and L after-effect:

```
tfn(q,D) = tf(q,D) · log₂(1 + c·avgdl/|D|)              (H2 length normalisation)

InL2(q,D) = (1 / (tfn + 1)) · tfn · log₂( (N + 1) / (n_q + 0.5) )

InL2(Q,D) = Σ_{q ∈ Q}  qtf(q,Q) · InL2(q,D)
```

Where:
- `tf(q,D)`, `tfn` as in PL2
- `n_q` = number of documents containing `q` (document frequency)
- `N` = total documents in the corpus
- `c > 0` = length-normalisation parameter (default 7.0 per Amati 2003, Table 4.10)
- `qtf(q,Q)` = query term frequency (often 1)
- `1/(tfn+1)` is the Laplace after-effect, downweighting later occurrences of the same term

## Starting weight preset
```python
"dfr_inl2.enabled": "true",
"dfr_inl2.ranking_weight": "0.0",
"dfr_inl2.c": "7.0",
```

## C++ implementation
- File: `backend/extensions/dfr_inl2.cpp`
- Entry: `double dfr_inl2_score(const uint32_t* query_term_ids, int n, const DocStats& doc, const CorpusStats& corp, double c);`
- Complexity: `O(|Q|)` per (query, doc); cheaper than PL2 — only one `log₂` per term inside the score
- Thread-safety: pure function
- SIMD: `#pragma omp simd reduction(+:score)`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/dfr_inl2.py::score_dfr_inl2(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.05 ms | < 0.5 ms |
| 100 | < 0.2 ms | < 5 ms |
| 500 | < 1 ms | < 25 ms |

## Diagnostics
- Raw InL2 score and per-term contributions
- C++ vs Python badge
- `n_q` and IDF-style log term per query term
- Length-normalised `tfn`

## Edge cases & neutral fallback
- `tf = 0` → term contributes 0
- `n_q = 0` (unseen term) → term contributes 0, flag `unseen_term`
- `|D| = 0` → 0.0, flag `empty_doc`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf → 0.0, flag `nan_clamped`
- `n_q ≥ N` (term in every doc) → log term clamped at 0 to avoid negative scores

## Minimum-data threshold
≥ 50 documents before `n_q` distribution is meaningful; below this returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <5 MB

## Scope boundary vs existing signals
FR-102 does NOT duplicate FR-101 PL2 because the basic model is `I(n)` (idf-style) rather than Poisson; on rare terms the two diverge by a factor of `log₂(N/n_q)` vs `log₂(N/F_q)`. It does not duplicate FR-010 rare-term propagation because FR-010 changes which docs hold a term, not how a term is scored.

## Test plan bullets
- unit tests: zero overlap, rare-term-only, common-term-only, single-term
- parity test: C++ vs Python within `1e-4`
- monotonicity: decreasing `n_q` (rarer term) should not decrease score for fixed `tf`
- no-crash test on adversarial input
- integration test: ranking unchanged when `ranking_weight = 0.0`
