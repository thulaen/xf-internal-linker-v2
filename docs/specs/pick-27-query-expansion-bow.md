# Pick #27 — BoW-PRF Query Expansion (Rocchio + Lavrenko-Croft)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 27 |
| **Canonical name** | Bag-of-words pseudo-relevance feedback query expansion |
| **Settings prefix** | `query_expansion_bow` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `63a8c1d` (PR-K, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/query_expansion_bow.py](../../backend/apps/pipeline/services/query_expansion_bow.py) |
| **Tests module** | [backend/apps/pipeline/test_query_expansion_bow.py](../../backend/apps/pipeline/test_query_expansion_bow.py) |
| **Benchmark module** | `backend/benchmarks/test_bench_query_expansion_bow.py` (pending G6) |

## 2 · Motivation

"Vocabulary mismatch" is the classic IR failure mode: the user asks
for "car" but the document says "automobile". A first-pass retrieval
surfaces a handful of top results; treating those as *pseudo-relevant*
and harvesting their vocabulary produces expansion terms the
second-pass retrieval can use to reach the "automobile" document.
Rocchio + Lavrenko-Croft give the math for weighting the original
query against the expansion evidence.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Rocchio, J. J. (1971). "Relevance feedback in information retrieval." *The SMART Retrieval System*, pp. 313-323. Lavrenko, V. & Croft, W. B. (2001). "Relevance-based language models." *SIGIR*, pp. 120-127. |
| **Open-access link** | Lavrenko-Croft: <https://ciir.cs.umass.edu/pubfiles/ir-205.pdf> |
| **Relevant section(s)** | Rocchio 1971 §2 — α/β/γ centroid combination; Lavrenko-Croft §4 — RM1/RM3 language-model PRF. |
| **What we faithfully reproduce** | Rocchio's α/β weighted sum (γ = 0 — we don't use negative-relevant evidence). Term ranking is Lavrenko-Croft-ish: avg TF in relevant set × `log(1+DF)` for breadth. |
| **What we deliberately diverge on** | No γ (non-relevant) term — Rocchio's paper discusses the trade-off; empirically γ > 0 hurts more often than it helps when we don't have explicit negative feedback. |

## 4 · Input contract

See `backend/apps/pipeline/services/query_expansion_bow.py`. Key API:

- **`expand(original_query_weights, pseudo_relevant_docs, *,
  top_terms=10, alpha=1.0, beta=0.75, stopwords=frozenset(),
  min_document_frequency=2) -> ExpandedQuery`**
- Empty docs list → query returned unchanged.

## 5 · Output contract

- `ExpandedQuery(weights: dict[str, float],
  expansion_terms: list[ExpansionTerm])`.
- Weights non-negative; original-query terms keep `alpha × w`,
  expansion terms get `beta × s`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `query_expansion_bow.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no expansion |
| `query_expansion_bow.top_n_docs` | int | `10` | Rocchio 1971 §3 — 10-20 is classical; > 30 adds noise | Yes | `int(5, 30)` | Larger = more expansion terms, more noise |
| `query_expansion_bow.top_expansion_terms` | int | `10` | Lavrenko-Croft §5 — beyond 20 terms NDCG plateaus | Yes | `int(3, 30)` | Too many drifts from intent; too few misses recall |
| `query_expansion_bow.alpha` | float | `1.0` | Rocchio default | Yes | `uniform(0.3, 2.0)` | Weight on original query |
| `query_expansion_bow.beta` | float | `0.75` | Rocchio's typical 0.5-0.8 range | Yes | `uniform(0.1, 1.5)` | Weight on expansion evidence |
| `query_expansion_bow.min_document_frequency` | int | `2` | Rocchio — pairs appearing in a single doc are too sparse | Yes | `int(1, 5)` | Higher filters sparse pairs |

## 7 · Pseudocode

See `apps/pipeline/services/query_expansion_bow.py`. Core:

```
function rank_expansion_terms(pseudo_relevant_docs, query_terms, top_n, stopwords, min_df):
    term_doc_freq, term_total_count = count over docs (filtering query/stopwords)
    for each term with df >= min_df:
        score = (total_count / N_docs) * log1p(df)
    return top_n by score

function expand(query_weights, pseudo_docs, top_n, alpha, beta, ...):
    terms = rank_expansion_terms(pseudo_docs, query_terms, top_n, ...)
    weights = {t: alpha*w for t, w in query_weights.items()}
    for exp in terms: weights[exp.term] += beta * exp.score
    return ExpandedQuery(weights, terms)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | First-pass top-N docs' term counts | Second-pass retrieval with expanded query; fused via RRF (pick #31) |

## 9 · Scheduled-updates job

None — per-query execution.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~10 MB per query expansion | — |
| Disk | 0 | — |
| CPU | ~5 ms per expansion | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_drops_query_terms_and_stopwords` | Filter logic |
| `test_respects_min_document_frequency` | Threshold |
| `test_ranked_descending_by_score` | Ordering |
| `test_original_query_weighted_by_alpha` | Math |
| `test_expansion_terms_weighted_by_beta` | Math |
| `test_shared_term_sums_alpha_and_beta_contributions` | Composition |
| `test_negative_weights_rejected` | Validation |
| `test_top_terms_caps_output` | Cap |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 docs × 100 terms | < 1 ms | > 10 ms |
| medium | 30 docs × 10 000 terms | < 50 ms | > 500 ms |
| large | 100 docs × 1 000 000 terms | < 10 s | > 60 s |

## 13 · Edge cases & failure modes

- **First-pass returns zero docs** → no expansion (helper returns
  original query).
- **All top-N docs share the same niche term** — that term dominates
  expansion; may drift from intent. Operators can tune `top_n_docs`
  down in that case.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| BM25 / semantic first-pass retriever | Produces the pseudo-relevant doc set |

| Downstream | Reason |
|---|---|
| #28 QL-Dirichlet | Alt scorer can use the expanded query |
| #31 RRF | Fuses original-query + expanded-query ranked lists |

## 15 · Governance checklist

- [ ] `query_expansion_bow.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-K)
- [ ] Benchmark module
- [x] Test module (PR-K)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
