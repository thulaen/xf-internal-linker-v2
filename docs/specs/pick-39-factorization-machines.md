# Pick #39 — Factorization Machines (Rendle 2010)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 39 |
| **Canonical name** | Factorization Machines — linear + feature-cross LTR |
| **Settings prefix** | `factorization_machines` |
| **Pipeline stage** | Score (ranking) |
| **Shipped in commit** | **DEFERRED** — needs `pyfm` / `libFM` pip dep |
| **Helper module** | `backend/apps/pipeline/services/factorization_machines.py` (Phase 6 — `apps.ranking.*` namespace from original plan is forbidden by anti-spaghetti rule §1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Plain linear models (LR, linear SVM) can't learn "feature A × feature B"
interactions without explicit cross-terms. Factorization Machines learn
low-rank interactions automatically — think of it as linear regression
plus a learned embedding for each feature whose dot product is the
interaction weight. Works on sparse features (like one-hot-encoded
domain IDs), scales linearly in training data.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Rendle, S. (2010). "Factorization machines." *ICDM*, pp. 995-1000. |
| **Open-access link** | <https://www.csie.ntu.edu.tw/~b97053/paper/Rendle2010FM.pdf> |
| **Relevant section(s)** | §2 — FM equation `y(x) = w_0 + <w,x> + Σ <v_i, v_j> x_i x_j`; §3 — training via SGD. |
| **What we faithfully reproduce** | FM with rank-k factorisation via `pyfm` / libFM. |

## 4 · Input contract

- **`train(X: scipy.sparse.csr_matrix, y: np.ndarray, *, rank=8,
  epochs=50, learning_rate=0.01, regularization=0.01)`**
- **`predict(X) -> np.ndarray`**

## 5 · Output contract

- Model with `.w0`, `.w`, `.V` (linear + interactions).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `factorization_machines.enabled` | bool | `true` (once dep approved) | Recommended preset policy | No | — | Off = no FM |
| `factorization_machines.rank` | int | `8` | Rendle 2010 §4 — rank 8-16 covers most use cases | Yes | `int(2, 64)` | Higher = more capacity |
| `factorization_machines.epochs` | int | `50` | Rendle 2010 §3 | Yes | `int(10, 500)` | More = better fit |
| `factorization_machines.learning_rate` | float | `0.01` | Rendle 2010 §3 | Yes | `loguniform(1e-4, 0.1)` | — |
| `factorization_machines.regularization` | float | `0.01` | Rendle 2010 §3 | Yes | `loguniform(1e-4, 0.1)` | — |

## 7 · Pseudocode

```
from pyfm import pylibfm

function train(X, y, rank, epochs, lr, reg):
    fm = pylibfm.FM(num_factors=rank, num_iter=epochs,
                    learning_rate=lr, regularization=reg,
                    task="regression")
    fm.fit(X, y)
    return fm
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Engineered ranker features as sparse matrix | Pairwise click probability |

## 9 · Scheduled-updates job

- **Key:** `factorization_machines_refit`
- **Cadence:** weekly (Sun 18:20)
- **Priority:** low
- **Estimate:** 10 min
- **Multicore:** yes (libFM)
- **RAM:** ≤ 128 MB

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~128 MB training | — |
| Disk | `rank × N_features × 4` bytes | — |
| CPU | 10 min weekly | — |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_trains_on_synthetic_data` | Canonical |
| `test_predict_shape_matches_input_rows` | Shape |
| `test_reproducible_under_seed` | Determinism |

## 12 · Benchmark inputs

Small/medium/large sparse matrices.

## 13 · Edge cases & failure modes

- **Dense features** — FM is for sparse; dense input hurts memory.
- **Non-stationary distribution** — weekly refit handles.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Ranker feature vectors | Training input |
| Click logs | Labels |

| Downstream | Reason |
|---|---|
| Ranker pairwise scorer | Primary consumer |

## 15 · Governance checklist

- [ ] Approve `pyfm` / libFM pip dep
- [ ] `factorization_machines.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module
- [ ] Benchmark module
- [ ] Test module
- [ ] `factorization_machines_refit` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
