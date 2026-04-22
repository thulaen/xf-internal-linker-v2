# Pick #42 — TPE hyperparameter optimiser (Bergstra 2011)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 42 |
| **Canonical name** | Tree-structured Parzen Estimator — Bayesian HPO via Optuna |
| **Settings prefix** | `meta_hpo` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **TO SHIP** — Option B approval received 2026-04-22. Needs `optuna` pip dep. |
| **Helper module** | `backend/apps/pipeline/services/meta_hpo.py` (to be created) |
| **Tests module** | `backend/apps/pipeline/test_meta_hpo.py` (to be created) |
| **Benchmark module** | `backend/benchmarks/test_bench_tpe.py` (pending G6) |

## 2 · Motivation

Every TPE-tuned hyperparameter in every pick spec (~60 of them across
the 52-pick roster) is pointless without a search mechanism. TPE is
the gold-standard Bayesian HPO: models P(hyperparameters | observed
quality) and P(hyperparameters | rest), then samples the ratio. Works
on mixed discrete/continuous/categorical search spaces, converges in
~200 trials on the linker's scale, robust to noisy objectives (like
offline NDCG on a sampled eval set).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Bergstra, J., Bardenet, R., Bengio, Y. & Kégl, B. (2011). "Algorithms for hyper-parameter optimization." *Advances in NIPS 24*, pp. 2546-2554. |
| **Open-access link** | <https://proceedings.neurips.cc/paper/2011/file/86e8f7ab32cfd12577bc2619bc635690-Paper.pdf> |
| **Relevant section(s)** | §3 — TPE formulation; §4 — empirical wins vs grid + random search. |
| **What we faithfully reproduce** | `optuna.samplers.TPESampler` (reference impl). |
| **What we deliberately diverge on** | Add `optuna.pruners.MedianPruner` to stop obviously bad trials early. |

## 4 · Input contract

- **`create_study(study_name: str, storage_url: str, direction="maximize")
  -> optuna.Study`**
- **`run(study, objective_fn, n_trials=200, timeout_seconds=None)`**
- Objective receives an `optuna.Trial` and calls `trial.suggest_float`,
  `trial.suggest_int`, `trial.suggest_categorical` to build its
  params.

## 5 · Output contract

- `study.best_params: dict[str, Any]` — the winning hyperparameters.
- `study.best_value: float` — the winning objective (e.g. NDCG@10).
- `study.trials_dataframe()` — full audit trail for the dashboard.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `meta_hpo.enabled` | bool | `true` | Option B approval 2026-04-22 | No | — | Off = picks use their hard-coded defaults |
| `meta_hpo.n_trials_per_week` | int | `200` | Bergstra §4 shows convergence by ~100 trials on SVM benchmarks; 200 gives margin for the linker's larger space | Yes | `int(50, 500)` | More trials = better convergence, longer job |
| `meta_hpo.timeout_seconds` | int | `7200` (2 h) | Fits inside the weekly Sunday HPO slot estimate | Yes | `int(600, 10800)` | Wall-clock cap |
| `meta_hpo.storage_url` | str | `"sqlite:///var/optuna/meta_hpo.db"` | Persisted across laptop reboots | No | — | Correctness (study persistence) |
| `meta_hpo.sampler` | str (enum) | `"tpe"` | Bergstra 2011 — the point of this pick | No | — | Alternative: `"random"` as fallback |
| `meta_hpo.pruner` | str (enum) | `"median"` | Optuna docs — median pruning saves ~30 % wall-clock on tall studies | No | — | Alternative: `"none"` |
| `meta_hpo.auto_apply_best_params` | bool | `false` | Operator approval required — dashboard shows the best trial; operator commits via "Accept HPO result" button | No | — | Safety rail |

## 7 · Pseudocode

```
import optuna

function create_study(name, storage, direction):
    return optuna.create_study(
        study_name=name, storage=storage, direction=direction,
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=5),
        load_if_exists=True,
    )

function run(study, objective_fn, n_trials, timeout):
    study.optimize(objective_fn, n_trials=n_trials, timeout=timeout)
    return study.best_params, study.best_value

function objective(trial):
    params = {}
    # Each pick spec contributes its TPE search space to this block
    params["rrf.k"] = trial.suggest_int("rrf.k", 10, 300)
    params["trustrank.damping"] = trial.suggest_float("trustrank.damping", 0.6, 0.95)
    params["cascade_click.prior_alpha"] = trial.suggest_float(
        "cascade_click.prior_alpha", 0.1, 5.0
    )
    # ... ~60 total params from the 52 specs
    return run_offline_ndcg_eval(params)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `backend/apps/pipeline/services/meta_hpo_eval.py` (to be created) | Reservoir-sampled eval set + current AppSetting preset | Offline NDCG@10 per trial |
| `backend/apps/suggestions/services/weight_preset_service.py` | Best-trial params | Operator-facing "Accept HPO result" button applies to AppSetting |

## 9 · Scheduled-updates job

- **Key:** `meta_hyperparameter_hpo`
- **Cadence:** weekly (Sun 16:45)
- **Priority:** high
- **Estimate:** 60–120 min
- **Multicore:** yes (each trial can fan out)
- **Depends on:** `weight_tuner_lbfgs_tpe` (ranker weights fit first)
- **RAM:** ≤ 256 MB
- **Disk:** `var/optuna/meta_hpo.db` (~50 MB after a year of weekly runs)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~200 MB peak (one objective evaluation) | — |
| Disk | ~50 MB after 1 year | Optuna audit |
| CPU | 60–120 min weekly | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_study_creation_sqlite_persists` | Cross-restart state |
| `test_best_params_contains_declared_search_space` | Correctness |
| `test_median_pruner_stops_bad_trials_early` | Efficiency |
| `test_auto_apply_disabled_does_not_touch_appsetting` | Safety rail |
| `test_manual_accept_applies_best_params` | Operator workflow |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 trials × toy objective | < 5 s | > 60 s |
| medium | 50 trials × simulated NDCG eval | < 3 min | > 15 min |
| large | 200 trials × real offline eval | 60–120 min | > 3 h |

## 13 · Edge cases & failure modes

- **Noisy objective** (offline NDCG variance ~1 %) — TPE handles via
  re-evaluation; fix seed per trial for reproducibility.
- **Discrete vs continuous mixing** — `suggest_int` / `suggest_float`
  / `suggest_categorical` handle all three.
- **Trial crashes** — Optuna marks the trial `FAILED` and continues;
  study robust to individual-trial failures.
- **SQLite corruption** — low-probability but recoverable by deleting
  the study file and restarting (loses history).

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Every pick with TPE-tuned hyperparameters | Provides the search space |
| #48 Reservoir Sampling | Eval set sampling |

| Downstream | Reason |
|---|---|
| Recommended preset via operator approval | Final destination |
| Dashboard "Accept HPO result" card | Operator UX |

## 15 · Governance checklist

- [ ] Add `optuna` pip dep + rebuild image
- [ ] `meta_hpo.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration creates `var/optuna/meta_hpo.db` directory
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] `meta_hyperparameter_hpo` scheduled job registered (W1)
- [ ] TPE search space collected from all pick specs
- [ ] Dashboard "Accept HPO result" card (W4)
