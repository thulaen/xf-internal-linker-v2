# FR-174 — Query Scope

## Overview
Query Scope is a *pre-retrieval* query-performance predictor that measures how *narrow* the query is in terms of corpus coverage. Concretely it is the negative log of the fraction of corpus documents containing at least one query term. A query that matches 1% of the corpus has high scope (specific); one that matches 80% has low scope (vague). For the internal-linker, scope flags host paragraphs whose key terms intersect with only a handful of candidate destinations — meaning a confident link suggestion is possible. Complements `fr173-simplified-clarity-score` (term-rarity in unigram LM) by being document-frequency-based rather than collection-frequency-based.

## Academic source
He, B. and Ounis, I. "A study of the dirichlet priors for term frequency normalisation." *Proceedings of the 28th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '05)*, pp. 465–471, 2005. DOI: `10.1145/1076034.1076128`. Predictor first introduced in: He & Ounis (2004), "Inferring query performance using pre-retrieval predictors." DOI: `10.1145/1008992.1009124`.

## Formula
From He & Ounis (2004), Section 3.3 — Query Scope is the negative log of the proportion of documents in the collection that contain *any* query term:

```
QS(Q) = − log( n_Q / N )

where
  n_Q = | { d ∈ C : Q ∩ d ≠ ∅ } |          (docs containing any query term)
  N   = |C|                                 (total docs in collection)
```

Equivalently in disjoint-event form on inverted-list lengths:

```
n_Q = | ⋃_{w ∈ Q} postings(w) |
QS(Q) = log(N) − log(n_Q)
```

Higher `QS(Q)` ⇒ smaller candidate set ⇒ more focused query.

## Starting weight preset
```python
"query_scope.enabled": "true",
"query_scope.ranking_weight": "0.0",
"query_scope.use_distinct_terms": "true",
"query_scope.empty_set_fallback": "neutral",
```

## C++ implementation
- File: `backend/extensions/query_scope.cpp`
- Entry: `double query_scope(const int* query_term_ids, int q_len, const PostingList* index, int total_docs)`
- Complexity: O(Σ |postings(w)|) for the union, with bitset shortcut for small `|Q|` (k-way OR over compressed bitmaps)
- Thread-safety: pure function; index is read-only
- Builds via pybind11; uses Roaring Bitmaps for posting union

## Python fallback
`backend/apps/pipeline/services/query_scope.py::compute_scope` using `set.union(*[postings[w] for w in Q])` then `−math.log(len(union)/N)`.

## Benchmark plan

| Size | |Q| · avg_postings | C++ target | Python target |
|---|---|---|---|
| Small | 5 · 1,000 | 0.05 ms | 1.0 ms |
| Medium | 20 · 50,000 | 1.5 ms | 35 ms |
| Large | 50 · 500,000 | 25 ms | 600 ms |

## Diagnostics
- Scope value rendered as "Scope: 6.4 (matches 1.6% of corpus)"
- Per-term posting size in debug pane
- C++/Python badge
- Debug fields: `n_q`, `total_docs_n`, `union_method` (bitset|set), `unseen_terms_count`

## Edge cases & neutral fallback
- `n_Q = 0` (no query term found anywhere) ⇒ undefined `log(0)` ⇒ neutral 0.5 with fallback flag
- `n_Q = N` (query covers entire corpus) ⇒ QS = 0 (perfectly vague)
- Empty query ⇒ neutral 0.5 with fallback flag
- Stopword removal: scope inflates artificially if all content terms are stopwords; require ≥1 non-stopword query term
- Repeated terms collapse via distinct-term toggle

## Minimum-data threshold
Need at least 1 in-vocabulary, non-stopword query term and `N ≥ 100` documents in the corpus before signal contributes.

## Budget
Disk: depends on inverted index (already paid for retrieval) · RAM: O(union bitmap) ≈ a few MB at N=1M

## Scope boundary vs existing signals
Distinct from `fr173-simplified-clarity-score` (uses collection unigram LM, not document frequency) and `fr176-avg-ictf-preretrieval-predictor` (collection-frequency based). Distinct from `fr011-field-aware-relevance-scoring` (per-document scorer). Pre-retrieval, document-frequency-based query specificity.

## Test plan bullets
- Unit: query of one term in 5/1000 docs returns QS = log(200) ≈ 5.30
- Unit: query of one term in 1000/1000 docs returns QS = 0
- Parity: C++ vs Python within 1e-6 on 500 queries
- Edge: zero-match query returns 0.5 with fallback flag
- Edge: empty query returns 0.5 with fallback flag
- Integration: deterministic across runs given fixed inverted index
- Regression: top-50 ranking unchanged when weight = 0.0
