# Pick #47 — Kernel SHAP explainability (Lundberg & Lee 2017)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 47 |
| **Canonical name** | Kernel SHAP — on-demand per-feature attribution |
| **Settings prefix** | `shap_explainer` |
| **Pipeline stage** | Eval / Explain |
| **Shipped in commit** | `f25104a` (PR-O, 2026-04-22). `shap==0.46.0` added to requirements.txt per operator approval. |
| **Helper module** | [backend/apps/pipeline/services/shap_explainer.py](../../backend/apps/pipeline/services/shap_explainer.py) |
| **Tests module** | [backend/apps/pipeline/test_explain_and_eval.py](../../backend/apps/pipeline/test_explain_and_eval.py) — `SHAPExplainerTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_shap.py` (pending G6) |

## 2 · Motivation

Operators need to answer "why did this suggestion score 0.82?". Kernel
SHAP decomposes the score into additive per-feature contributions:
`score = baseline + Σ φ_f`. An operator clicks Explain; the UI shows
"0.40 from BM25, 0.25 from PageRank, 0.15 from freshness, 0.02 from
diversity". Lundberg & Lee 2017 prove this decomposition is unique
under mild axioms (local accuracy, missingness, consistency).

**On-demand only.** 50-100 MB peak RAM per call; never scheduled.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Lundberg, S. M. & Lee, S.-I. (2017). "A unified approach to interpreting model predictions." *NIPS 30*, pp. 4765-4774. |
| **Open-access link** | <https://arxiv.org/abs/1705.07874> |
| **Relevant section(s)** | §4 — Kernel SHAP coalitions; §4.3 — additive-guarantee axioms. |
| **What we faithfully reproduce** | `shap.KernelExplainer` is the paper's reference impl. Wrapper adds tidy API + tests. |
| **What we deliberately diverge on** | Sort contributions by |SHAP| for UI rendering; lib returns unsorted arrays. |

## 4 · Input contract

- **`explain(*, score_fn, subject, background, feature_names,
  nsamples=200) -> Explanation`**
- `score_fn` must accept `(batch, n_features)` arrays.
- `subject` is a single row `(n_features,)`.
- `background` is a representative sample `(n_bg, n_features)`.
- Raises `SHAPUnavailable` if `shap` not installed.

## 5 · Output contract

- `Explanation(predicted_value, baseline, contributions: list[FeatureContribution])`.
- `contributions` sorted by descending `|shap_value|`.
- **Additive:** `baseline + Σ shap_values ≈ predicted_value` (within
  Kernel-SHAP sampling noise).
- **Determinism.** Kernel SHAP samples coalitions; fix its internal
  seed for reproducibility (library default is deterministic).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `shap_explainer.enabled` | bool | `true` | Recommended preset policy — dep approved | No | — | Off = Explain button hidden |
| `shap_explainer.nsamples` | int | `200` | Lundberg-Lee §4.2 recommend `2M+2048` but 200 is plenty for our 10-30 feature space | No | — | Correctness (sampling precision) |
| `shap_explainer.background_size` | int | `100` | Lundberg-Lee §3 — 100 representative rows is the standard baseline set size | No | — | Larger = more stable baseline, slower |
| `shap_explainer.max_peak_ram_mb` | int | `200` | Guard-rail — abort explanation if background × subject batch blows past this | No | — | Safety |

**All params fixed** — Kernel SHAP is a correctness primitive, not
a ranking-quality knob.

## 7 · Pseudocode

See `apps/pipeline/services/shap_explainer.py`. Core:

```
import shap

function explain(score_fn, subject, background, feature_names, nsamples):
    validate shapes
    explainer = shap.KernelExplainer(score_fn, background, silent=True)
    shap_values = explainer.shap_values(subject.reshape(1, -1), nsamples=nsamples)
    baseline = explainer.expected_value
    contributions = [FeatureContribution(name, value, shap_value)
                     for name, value, shap_value in zip(feature_names, subject, shap_values)]
    contributions.sort(key=lambda c: -abs(c.shap_value))
    return Explanation(predicted=baseline + sum(shap_values), baseline=baseline,
                       contributions=contributions)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| (W4) New endpoint `POST /api/suggestions/<id>/explain` | Suggestion ID | Returns the `Explanation` JSON to the UI |
| (W4) Angular Explain button | Suggestion ID | Renders top-5 contributions in a panel |

**Wiring status.** Helper exists (PR-O). Endpoint + UI land in W4.
Also requires the production ranker to expose its `score_fn` as a
pure callable; currently it's embedded in the pipeline (refactor
planned for W4).

## 9 · Scheduled-updates job

**None — explicitly on-demand only.** Calling from the scheduled
runner would blow the 13-23 window's compute budget and produce no
actionable output.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (peak) | 50-100 MB per explanation | lib docs |
| Disk | ~60 MB install (shap + numba + llvmlite) | — |
| CPU | ~1-5 s per explanation on 10-30 features | benchmark small |

## 11 · Tests

All 8 `SHAPExplainerTests` pass.

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10-feature subject × 50-row background | < 500 ms | > 5 s |
| medium | 30-feature × 500-row background | < 5 s | > 60 s |
| large | 100-feature × 1000-row background | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **`shap` not installed** → `SHAPUnavailable`. Dashboard shows the
  Explain button as disabled with a tooltip.
- **Mismatched feature count** → `ValueError`.
- **Empty background** → `ValueError`.
- **Score function that is itself random** — SHAP averages out the
  randomness, but residual variance is higher; increase `nsamples`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Any scoring function (ranker, calibration, RRF) | Is the target of explanation |

| Downstream | Reason |
|---|---|
| UI Explain panel | Rendering consumer |

## 15 · Governance checklist

- [x] `shap==0.46.0` in requirements.txt
- [ ] `shap_explainer.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (50-100 MB peak)
- [x] Helper module (PR-O)
- [ ] Benchmark module
- [x] Test module (PR-O)
- [ ] `/api/suggestions/<id>/explain` endpoint (W4)
- [ ] Angular Explain button (W4)
- [ ] Ranker `score_fn` exposed as pure callable (W4)
