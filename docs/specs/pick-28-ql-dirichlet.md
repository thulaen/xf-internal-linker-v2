# Pick #28 — Query Likelihood + Dirichlet smoothing (Zhai-Lafferty 2001)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 28 |
| **Canonical name** | Query-likelihood retrieval with Dirichlet-smoothed language models |
| **Settings prefix** | `query_likelihood` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `63a8c1d` (PR-K, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/query_likelihood.py](../../backend/apps/pipeline/services/query_likelihood.py) |
| **Tests module** | [backend/apps/pipeline/test_query_likelihood.py](../../backend/apps/pipeline/test_query_likelihood.py) |
| **Benchmark module** | `backend/benchmarks/test_bench_query_likelihood.py` (pending G6) |

## 2 · Motivation

Pure BM25 can miss when a query term is rare in the corpus (its IDF
weight dominates, docs without that exact token lose). Query-Likelihood
answers the complementary question: *how probable is the query under
this document's language model?* Dirichlet smoothing pulls short-doc
LMs toward the corpus baseline so a single missing term doesn't
catastrophically zero the score. Zhai & Lafferty 2001 show QL-Dirichlet
pairs well with BM25 via rank fusion — together they beat either alone
across TREC benchmarks.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Zhai, C. & Lafferty, J. (2001). "A study of smoothing methods for language models applied to ad hoc information retrieval." *SIGIR*, pp. 334-342. |
| **Open-access link** | <http://sifaka.cs.uiuc.edu/~zhai/pub/sigir01.pdf> |
| **Relevant section(s)** | §3 — Dirichlet formula `P(t|θ_D) = (tf_d + μP(t|C)) / (|D|+μ)`; §5.2 — μ = 2000 empirical default. |
| **What we faithfully reproduce** | The smoothed LM + `Σ n(t,Q) log P(t|θ_D)` scoring. |
| **What we deliberately diverge on** | We use a minimum collection-probability floor `1e-10` for unseen terms (the paper leaves this unspecified). |

## 4 · Input contract

See `apps/pipeline/services/query_likelihood.py`. Key API:

- **`CollectionStatistics(collection_term_counts, collection_length)`**
- **`score_document(*, query_term_counts, document_term_counts,
  document_length, statistics, mu=2000.0) -> QueryLikelihoodScore`**
- **`dirichlet_smoothed_probability(term, document_term_counts,
  document_length, statistics, mu) -> float`**

## 5 · Output contract

- `QueryLikelihoodScore(log_score: float, per_term: dict)`.
- `log_score ≤ 0` (sum of log-probabilities).
- **Invariants.**
  - Empty query → `log_score=0`, `per_term={}`.
  - Higher term overlap → higher (less-negative) log_score.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `query_likelihood.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no QL scoring |
| `query_likelihood.dirichlet_mu` | float | `2000.0` | Zhai-Lafferty §5.2 — empirical sweet spot for mixed-length TREC data | Yes | `loguniform(100.0, 10000.0)` | Higher = more smoothing toward collection baseline |
| `query_likelihood.min_collection_probability` | float | `1e-10` | Implementation floor for unseen terms | No | — | Correctness (prevents log(0)) |

## 7 · Pseudocode

See `apps/pipeline/services/query_likelihood.py`. Core:

```
function dirichlet_smoothed_probability(t, doc_counts, doc_len, stats, mu):
    p_collection = max(stats.collection_term_counts[t] / stats.collection_length, 1e-10)
    return (doc_counts.get(t, 0) + mu * p_collection) / (doc_len + mu)

function score_document(Q_counts, D_counts, D_len, stats, mu):
    log_score = 0.0
    per_term = {}
    for t, q_count in Q_counts.items():
        p = dirichlet_smoothed_probability(t, D_counts, D_len, stats, mu)
        c = q_count * log(p)
        per_term[t] = c
        log_score += c
    return QueryLikelihoodScore(log_score, per_term)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Query + candidate doc stats | QL-Dirichlet score feeds RRF fusion alongside BM25 |

## 9 · Scheduled-updates job

None directly — but the `collection_term_counts` and
`collection_length` statistics are refreshed daily by the ranker's
stats-refresh job (part of W3 wiring).

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~50 MB for the collection stats table (10M vocab × 8 bytes) | — |
| Disk | 50 MB | — |
| CPU | ~100 µs per (query, doc) pair | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_known_term_returns_ratio` | Collection prob correct |
| `test_unseen_term_floored_positive` | Min floor |
| `test_unseen_in_doc_still_nonzero` | Smoothing works |
| `test_known_term_pulled_toward_collection_by_mu` | μ → ∞ limit |
| `test_doc_with_more_query_terms_scores_higher` | Direction |
| `test_per_term_sum_equals_log_score` | Decomposition |
| `test_score_is_non_positive` | Invariant |
| `test_empty_query_scores_zero` | Degenerate |
| `test_negative_mu_rejected` | Validation |
| `test_zero_collection_length_rejected` | Validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 query × 100 docs | < 10 ms | > 100 ms |
| medium | 100 queries × 10 000 docs | < 30 s | > 5 min |
| large | 10 000 queries × 1 000 000 docs | < 1 h | > 10 h |

## 13 · Edge cases & failure modes

- **Doc length zero** → smoothing falls back to pure collection prob
  (`doc_len + mu = mu`).
- **Query term never in corpus** → floor kicks in; contribution is
  `q_count × log(1e-10)`.
- **Very short query** (1-2 terms) — QL-Dirichlet's variance is high;
  pair with BM25 via RRF to stabilise.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #27 Query Expansion | Operator can feed expanded query terms |
| Corpus stats refresh | Computes collection_term_counts |

| Downstream | Reason |
|---|---|
| #31 RRF | Fuses QL-Dirichlet ranking with BM25 ranking |

## 15 · Governance checklist

- [ ] `query_likelihood.enabled` seeded
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
