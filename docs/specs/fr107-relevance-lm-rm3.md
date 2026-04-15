# FR-107 - Relevance Language Model (RM3)

## Overview
Anchor texts are short (often 2-4 words). Short queries miss documents that use synonyms or related vocabulary. RM3 is the canonical pseudo-relevance-feedback expansion: estimate a relevance language model from the top-`k` documents returned by an initial scorer, then mix it with the original query model. The expanded query catches related vocabulary that the literal anchor text misses. Complements FR-009 learned anchor vocabulary because RM3 is corpus-driven and per-query while FR-009 is offline and per-anchor.

## Academic source
**Lavrenko, Victor and Croft, W. Bruce (2001).** "Relevance-Based Language Models." *Proceedings of the 24th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2001)*, pp. 120-127. DOI: `10.1145/383952.383972`. (RM3 mixing variant defined in: **Abdul-Jaleel et al. (2004).** "UMass at TREC 2004: Novelty and HARD," *TREC 2004 Notebook*.)

## Formula
From Lavrenko & Croft (2001), Eq. 3 (RM1) plus Abdul-Jaleel et al. (2004) RM3 mixing:

```
RM1:  p(w | R) ∝ Σ_{D ∈ F_k}  p(w | D) · p(Q | D)

      p(Q | D) = ∏_{q ∈ Q} p(q | D)                  (with smoothing as in FR-105)

RM3:  p(w | Q') = (1 − α) · p_MLE(w | Q) + α · p_RM1(w | R)

      score_RM3(D) = − KL( p(· | Q') ‖ p(· | D) )
                   = Σ_{w}  p(w | Q') · log p(w | D)
```

Where:
- `F_k` = top-`k` documents from the initial run (default `k = 10` per Lavrenko & Croft §5)
- `p(w|D)` = Dirichlet-smoothed document model (use FR-105 stage-1)
- `p_MLE(w|Q) = qtf(w,Q) / |Q|`
- `p_RM1(w|R)` = relevance model estimate, normalised over the top-`k` docs
- `α ∈ [0, 1]` = original-vs-expansion mix weight (default 0.5 per Abdul-Jaleel §3)
- Expansion vocabulary truncated to top-`m` terms by `p_RM1` (default `m = 50`)

## Starting weight preset
```python
"rm3.enabled": "true",
"rm3.ranking_weight": "0.0",
"rm3.k_feedback_docs": "10",
"rm3.m_expansion_terms": "50",
"rm3.alpha_mix": "0.5",
```

## C++ implementation
- File: `backend/extensions/rm3.cpp`
- Entry: `std::vector<float> rm3_expand(const uint32_t* query_term_ids, int n, const TopKDocs& fk, const CorpusStats& corp, int m, double alpha);` — returns expanded weighted query; the rerank pass reuses any base scorer
- Complexity: `O(k · |D̄|)` for RM1 estimation + `O(m · log m)` for top-`m` selection, where `|D̄|` is mean doc length in top-`k`
- Thread-safety: pure function
- SIMD: weight aggregation across docs vectorised
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/rm3.py::expand_rm3(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 (k=10) | < 1 ms | < 10 ms |
| 100 (k=10) | < 3 ms | < 30 ms |
| 500 (k=10) | < 8 ms | < 80 ms |

(`k` dominates cost more than candidate-count.)

## Diagnostics
- Top-`m` expansion terms with their `p_RM1(w|R)` weights
- C++ vs Python badge
- `α` actually used after any per-query auto-update
- Whether the expansion changed the ranking vs the base scorer

## Edge cases & neutral fallback
- `|F_k| < 2` (too few feedback docs) → return original query unchanged, flag `insufficient_feedback`
- All `p(Q|D) = 0` (no doc supports the query) → return original, flag `no_evidence`
- `α = 0` → reduces to original query, flagged `alpha_zero`
- Missing corpus stats → neutral 0.5, flag `no_corpus_stats`
- NaN / Inf in any term weight → drop that term, flag `nan_clamped`

## Minimum-data threshold
Top-`k` must contain ≥ `min(k, 5)` documents with non-trivial `p(Q|D)`; below this RM3 returns the unexpanded query.

## Budget
Disk: <2 MB  ·  RAM: <20 MB (top-`k` document term-vectors held in memory during expansion)

## Scope boundary vs existing signals
FR-107 does NOT duplicate FR-009 learned anchor vocabulary because RM3 is per-query (built fresh from top-`k`) while FR-009 is per-anchor (precomputed). It does not duplicate FR-018 query-time tuning because RM3 modifies the query, not the ranker weights.

## Test plan bullets
- unit tests: top-`k` empty, top-`k` all identical, top-`k` diverse
- parity test: C++ vs Python expansion vectors within `1e-4`
- monotonicity: expansion never removes original query terms (their weight is `(1−α)` floor)
- no-crash test on adversarial input (huge `k`, single-token docs)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- semantic test: synonym present in corpus appears among top-`m` expansion terms
