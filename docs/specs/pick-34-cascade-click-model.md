# Pick #34 — Cascade Click Model (Craswell et al. 2008)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 34 |
| **Canonical name** | Cascade click model |
| **Settings prefix** | `cascade_click` |
| **Pipeline stage** | Score (relevance estimation from clicks) |
| **Shipped in commit** | `879ecc5` (PR-N, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/cascade_click_model.py](../../backend/apps/pipeline/services/cascade_click_model.py) |
| **Tests module** | [backend/apps/pipeline/test_feedback_signals.py](../../backend/apps/pipeline/test_feedback_signals.py) — `CascadeClickTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_cascade_click.py` (pending G6) |

## 2 · Motivation

A click at position 3 doesn't mean "position 4+ are bad" — the user
probably never *looked* at positions 4+. Naive "clicked vs not"
aggregates label position 4 as a negative, which is wrong. Cascade
says: user scans from top, clicks with probability `r_i` on each
position, stops on click. So positions above the click = examined
(labelled); positions below the click = unexamined (skipped from the
aggregate). This gives unbiased per-doc relevance estimates.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Craswell, N., Zoeter, O., Taylor, M. & Ramsey, B. (2008). "An experimental comparison of click position-bias models." *WSDM*, pp. 87-94. |
| **Open-access link** | <https://www.microsoft.com/en-us/research/wp-content/uploads/2008/06/wsdm2008.pdf> |
| **Relevant section(s)** | §3.2 — Cascade model definition; §4 — MLE derivation. |
| **What we faithfully reproduce** | Examination semantics + Laplace smoothing. |
| **What we deliberately diverge on** | We expose raw examinations + clicks alongside the smoothed relevance so operators can see the counts. |

## 4 · Input contract

- **`ClickSession(ranked_docs, clicked_rank)`** — session record.
  `clicked_rank` is 1-based or `None`.
- **`estimate(sessions, *, prior_alpha=1.0, prior_beta=1.0) ->
  dict[DocId, DocRelevance]`**
- Out-of-range clicked_rank → `ValueError`.

## 5 · Output contract

- `DocRelevance(doc_id, relevance, examinations, clicks)`.
- `relevance` = `(clicks + α) / (examinations + α + β)`.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `cascade_click.enabled` | bool | `true` | Recommended preset policy | No | — | Off = raw CTR aggregates |
| `cascade_click.prior_alpha` | float | `1.0` | Laplace prior — standard Beta(1,1) mean 0.5 | Yes | `uniform(0.1, 5.0)` | Higher = prior pulls toward mean click rate |
| `cascade_click.prior_beta` | float | `1.0` | Same | Yes | `uniform(0.1, 5.0)` | Same |
| `cascade_click.min_sessions_per_doc` | int | `10` | Empirical — below ~10 observations relevance estimate variance is huge | Yes | `int(1, 100)` | Higher = fewer docs in output, more confident each |

## 7 · Pseudocode

See `apps/pipeline/services/cascade_click_model.py`. Core:

```
function estimate(sessions, alpha, beta):
    examinations = {}; clicks = {}
    for session in sessions:
        if session.clicked_rank is not None:
            examined_depth = session.clicked_rank
            validate clicked_rank <= len(session.ranked_docs)
        else:
            examined_depth = len(session.ranked_docs)
        for i, doc in enumerate(session.ranked_docs[:examined_depth], start=1):
            examinations[doc] += 1
            if session.clicked_rank == i:
                clicks[doc] += 1
    return {doc: DocRelevance(doc, (c+alpha)/(e+alpha+beta), e, c) for ...}
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/feedback_rerank.py` | Click sessions → relevance estimates | Reranking signal based on debiased CTR |
| `apps/analytics/impact_engine.py` | Click logs | Unbiased per-doc quality metric |

## 9 · Scheduled-updates job

- **Key:** `cascade_click_em_re_estimate`
- **Cadence:** weekly (Sun 18:00)
- **Priority:** low
- **Estimate:** 5 min
- **Multicore:** no
- **RAM:** ≤ 32 MB
- **Disk:** relevance table size scales with N docs observed

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~10 MB per 100k sessions | — |
| Disk | Relevance table | — |
| CPU | ~1 ms per 1000 sessions | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_click_boosts_relevance` | Direction |
| `test_only_examined_positions_tracked` | Cascade semantics |
| `test_no_click_means_full_scan` | Semantics |
| `test_out_of_range_click_rejected` | Validation |
| `test_prior_mean_uniform_default` | Prior math |
| `test_smoothing_prior_prevents_zero_rel` | Laplace works |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 sessions | < 1 ms | > 10 ms |
| medium | 100 000 sessions | < 100 ms | > 1 s |
| large | 10 000 000 sessions | < 10 s | > 2 min |

## 13 · Edge cases & failure modes

- **Empty sessions** → empty dict.
- **Session with empty ranked_docs** → skipped silently.
- **Pathological all-clicks-at-position-1 data** — only position-1
  docs get counted; depth-2+ docs unobserved.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Click logs | Source data |
| #33 IPS | Alternative debiasing — stack both for robust estimates |

| Downstream | Reason |
|---|---|
| Feedback reranker | Primary consumer |
| #35 Elo | Pairwise signals from cascade (clicked > skipped) |

## 15 · Governance checklist

- [ ] `cascade_click.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-N)
- [ ] Benchmark module
- [x] Test module (PR-N)
- [x] `cascade_click_em_re_estimate` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Feedback reranker wired (W3)
