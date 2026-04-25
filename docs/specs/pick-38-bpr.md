# Pick #38 — Bayesian Personalized Ranking (Rendle 2009)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 38 |
| **Canonical name** | BPR — Bayesian Personalized Ranking from implicit feedback |
| **Settings prefix** | `bpr` |
| **Pipeline stage** | Score (ranking LTR) |
| **Shipped in commit** | **DEFERRED** — needs `implicit` pip dep |
| **Helper module** | `backend/apps/pipeline/services/bpr_ranker.py` (Phase 6 — `apps.ranking.*` namespace from original plan is forbidden by anti-spaghetti rule §1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Click-through is implicit positive signal: "user clicked A over B".
BPR formalises this as a pairwise loss — the model must rank clicked
items higher than skipped items. Works without explicit ratings, scales
to millions of (user, item) interactions, and typically beats
point-wise regression on ranking metrics.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Rendle, S., Freudenthaler, C., Gantner, Z. & Schmidt-Thieme, L. (2009). "BPR: Bayesian personalized ranking from implicit feedback." *UAI*. |
| **Open-access link** | <https://arxiv.org/abs/1205.2618> |
| **Relevant section(s)** | §3 — BPR-Opt loss; §4 — SGD with pairwise sampling. |
| **What we faithfully reproduce** | Use `implicit.BayesianPersonalizedRanking` library. |

## 4 · Input contract

- **`train(interactions: scipy.sparse.csr_matrix, *, factors=64,
  iterations=100, learning_rate=0.01, regularization=0.01)`** —
  implicit-feedback user×item matrix.
- **`recommend(user_id) -> list[(item_id, score)]`**

## 5 · Output contract

- Model object with `.user_factors`, `.item_factors`, `.recommend`.
- **Determinism.** Random init; set seed for reproducibility.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `bpr.enabled` | bool | `true` (once dep approved) | Recommended preset policy | No | — | Off = no BPR |
| `bpr.factors` | int | `64` | Rendle 2009 §6 — 64 on MovieLens | Yes | `int(16, 256)` | Higher = more capacity |
| `bpr.iterations` | int | `100` | Rendle 2009 §6 | Yes | `int(20, 500)` | More = better fit, slower |
| `bpr.learning_rate` | float | `0.01` | Rendle 2009 §6 | Yes | `loguniform(1e-4, 0.1)` | Higher = faster convergence / more volatile |
| `bpr.regularization` | float | `0.01` | Rendle 2009 §6 | Yes | `loguniform(1e-4, 0.1)` | Higher = more regularisation |

## 7 · Pseudocode

```
import implicit
from scipy.sparse import csr_matrix

function train(interactions_csr, factors, iterations, lr, reg):
    model = implicit.bpr.BayesianPersonalizedRanking(
        factors=factors, iterations=iterations,
        learning_rate=lr, regularization=reg,
    )
    model.fit(interactions_csr)
    return model
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | User-item interactions | BPR latent factors as ranking feature |

## 9 · Scheduled-updates job

- **Key:** `bpr_refit`
- **Cadence:** weekly (Sun 18:40)
- **Priority:** low
- **Estimate:** 15 min
- **Multicore:** yes
- **RAM:** ≤ 128 MB @ 1M users × 1M items

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~128 MB training | implicit docs |
| Disk | `factors × 4 bytes × (N_users + N_items)` | — |
| CPU | 15 min weekly | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_trains_on_synthetic_matrix` | Canonical |
| `test_recommend_returns_items` | API |
| `test_reproducible_under_seed` | Determinism |

## 12 · Benchmark inputs

Small/medium/large matrices as per implicit docs.

## 13 · Edge cases & failure modes

- **Sparse users** (1-2 interactions) — BPR underperforms; provide a
  cold-start fallback (e.g. popularity baseline).

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #34 Cascade | Click logs become interaction matrix |

| Downstream | Reason |
|---|---|
| Ranker latent-factor feature | Primary consumer |

## 15 · Governance checklist

- [ ] Approve `implicit` pip dep
- [ ] `bpr.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module
- [ ] Benchmark module
- [ ] Test module
- [ ] `bpr_refit` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
