# Pick #41 — L-BFGS-B weight optimiser (Byrd-Lu-Nocedal-Zhu 1995)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 41 |
| **Canonical name** | L-BFGS-B — limited-memory quasi-Newton optimiser with box bounds |
| **Settings prefix** | `lbfgs_b` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **REUSED** — already in production via `scipy.optimize.minimize` at [apps/suggestions/services/weight_tuner.py:81](../../backend/apps/suggestions/services/weight_tuner.py) |
| **Helper module** | `scipy.optimize.minimize(method="L-BFGS-B")` wrapped in `apps/suggestions/services/weight_tuner.py` |
| **Tests module** | existing weight-tuner tests |
| **Benchmark module** | `backend/benchmarks/test_bench_lbfgs.py` (pending G6) |

## 2 · Motivation

Fit ranking weights to minimise a loss (typically cross-entropy on
(feature, label) pairs). Simple gradient descent is slow to converge;
Newton's method needs the Hessian (too big for 100-dim weight
vectors). L-BFGS-B approximates the Hessian from the recent gradient
history — fast convergence on smooth convex losses, handles box
constraints (weights ∈ [0, 1]).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Byrd, R. H., Lu, P., Nocedal, J. & Zhu, C. (1995). "A limited memory algorithm for bound constrained optimization." *SIAM Journal on Scientific Computing* 16(5): 1190-1208. |
| **Open-access link** | <https://epubs.siam.org/doi/10.1137/0916069> (paywall); SciPy implementation: <https://github.com/scipy/scipy/blob/main/scipy/optimize/lbfgsb_py.py> |
| **Relevant section(s)** | §2 — L-BFGS recurrence; §3 — bound-constrained variant. |
| **What we faithfully reproduce** | SciPy's `minimize(method="L-BFGS-B")` is a faithful port of the Fortran reference. |

## 4 · Input contract

- **Objective** `fn(params: np.ndarray) -> float`.
- **Gradient** (optional, finite-differenced if absent).
- **`x0: np.ndarray`** — initial params.
- **`bounds: list[tuple[float, float]]`** — per-param box constraints.

## 5 · Output contract

- `OptimizeResult` with `.x`, `.fun`, `.success`, `.nfev`, `.message`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `lbfgs_b.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no auto-tuning |
| `lbfgs_b.maxiter` | int | `15000` | SciPy default; weight_tuner.py uses it unchanged | Yes | `int(100, 50000)` | Iteration cap |
| `lbfgs_b.ftol` | float | `2.22e-9` | SciPy default; machine-precision floor on change in objective | No | — | Correctness / convergence |
| `lbfgs_b.gtol` | float | `1e-5` | SciPy default | Yes | `loguniform(1e-7, 1e-3)` | Gradient-tolerance stop condition |

## 7 · Pseudocode

```
from scipy.optimize import minimize

function optimise(fn, x0, bounds, grad=None):
    result = minimize(fn, x0=x0, args=(...), method="L-BFGS-B",
                      jac=grad, bounds=bounds,
                      options={"maxiter": MAXITER, "ftol": FTOL, "gtol": GTOL})
    return result
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/suggestions/services/weight_tuner.py:81` | Ranking weights + loss + bounds | New weight values |
| `apps/pipeline/services/platt_calibration.py` | Platt's 2-param MLE | Sigmoid fit |

## 9 · Scheduled-updates job

- **Key:** `weight_tuner_lbfgs_tpe`
- **Cadence:** weekly (Sun 16:00)
- **Priority:** high
- **Estimate:** 20–40 min
- **Multicore:** yes (parallel gradient computation when available)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | Linear in param count + gradient history (~m × 8 × dim) | — |
| Disk | 0 | — |
| CPU | Dominated by objective evaluation; optimiser is < 10 % | benchmark medium |

## 11 · Tests

Existing weight-tuner tests cover the wrapper. Direct helper tests
(pending): `test_minimises_convex_quadratic`, `test_bounds_respected`,
`test_infeasible_initial_point_raises`.

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10-dim quadratic | < 10 ms | > 100 ms |
| medium | 100-dim ranking-weight fit | < 1 s | > 10 s |
| large | 1 000-dim with 100k training pairs | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **Non-convex loss** — L-BFGS-B may converge to a local min. Use TPE
  (pick #42) as the global-search outer loop.
- **Numerical NaN in gradient** — `OptimizeResult.success=False`;
  caller must handle.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Loss function, training data | — |

| Downstream | Reason |
|---|---|
| #32 Platt | Uses L-BFGS-B for its 2-param fit |
| #42 TPE | Outer HPO layer wraps L-BFGS-B as an inner fit |

## 15 · Governance checklist

- [ ] `lbfgs_b.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] In use (weight_tuner.py)
- [ ] Direct benchmark module
- [x] Existing tests cover it
- [ ] TPE search space declared
