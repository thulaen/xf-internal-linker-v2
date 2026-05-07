# FR-245 — Calibrated similarity threshold via Platt scaling

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Platt-calibrated cosine probability + decision threshold |
| **Settings prefix** | `pipeline.calibration_enabled`, `pipeline.min_calibrated_probability`, `pipeline.calibration_recalibration_cadence_days`, `pipeline.calibration_validation_set_min_size` |
| **Pipeline stage** | Stage-2 cutoff (replaces hardcoded `pipeline.min_semantic_score`) |
| **Helpers** | `apps.pipeline.services.score_calibration.calibrated_probability`, `passes_calibrated_threshold`, `fit_platt_sigmoid`, `get_calibration_status` |
| **Default state** | **ON.** Uses cold-start logistic params (A=6.0, B=-1.5) until a fitted sigmoid is available. Cold-start params target the historical 0.25-cosine cutoff at the 0.5-probability decision boundary, so behaviour is roughly equivalent to today's hardcoded threshold but expressed as a calibrated probability. |

## 2 · Motivation (ELI5)

Today the pipeline keeps a candidate when its raw cosine ≥ 0.25. That number was picked by feel — no spec, no per-corpus adaptation. A calibrated threshold maps the cosine to "P(this is a good match)" using a sigmoid fitted against accept/reject feedback. Operators tune one number (`pipeline.min_calibrated_probability = 0.5`) instead of guessing what cosine cutoff is right for their content.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Platt, J. C. (1999). *Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods.* Advances in Large Margin Classifiers. https://citeseerx.ist.psu.edu/doc/10.1.1.41.1639. The canonical sigmoid-fit method. §2.4 — class-conditional smoothing prevents fit collapse on small validation sets. |
| **Modern evidence** | Guo, C. et al. (2017). *On Calibration of Modern Neural Networks.* ICML 2017. arXiv:[1706.04599](https://arxiv.org/abs/1706.04599). §5 — Platt-scaling generalises to deep models; recommends 30-day recalibration cadence. |
| **Validation set size** | Niculescu-Mizil, A. & Caruana, R. (2005). *Predicting Good Probabilities with Supervised Learning.* ICML. DOI:[10.1145/1102351.1102430](https://doi.org/10.1145/1102351.1102430). §4 — minimum 1000 pairs for stable fit. |

## 4 · Output contract

`calibrated_probability(cosine_score, *, params=None) -> float`
- Returns `σ(A·cosine + B)` ∈ (0, 1) using the standard sigmoid convention.
- `params` defaults to cold-start (A=6.0, B=-1.5).

`passes_calibrated_threshold(cosine_score, *, threshold=0.5, params=None) -> bool`
- True iff `calibrated_probability(...) >= threshold`.

`fit_platt_sigmoid(scores, labels, ...) -> Optional[PlattParams]`
- Newton-Raphson fit minimising the BCE loss with Platt's class-conditional smoothing (Platt 1999 §2.4).
- Returns None when |scores| < 1000 OR labels are degenerate (all-pos or all-neg).

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/score_calibration.py` | New file. ~170 lines. Numerically-stable sigmoid + bounded Newton fit. |
| `backend/apps/pipeline/tests_scaffolds.py::PlattCalibrationTests` | 9 tests. |

Settings keys (`pipeline.calibration_*`) seeded by migration 0061.

## 6 · Test plan

9 SimpleTestCase tests:
1. **Constants locked** — Niculescu-Mizil 2005 §4 + Platt 1999 §2.
2. **Probability in unit interval** for canonical cosines.
3. **Monotonicity** — higher cosine → higher P under cold-start.
4. **Cold-start decision boundary near historical 0.25 cutoff** (P(0.25) ≈ 0.5).
5. **Threshold passes/fails** at default 0.5.
6. **Fit below minimum returns None** — Niculescu-Mizil §4.
7. **Fit with degenerate labels returns None** — Platt §2.2.
8. **Fit on synthetic logistic dataset returns params**.
9. **Length mismatch raises ValueError**.

## 7 · Wire-in (deferred)

The current cutoff site is `pipeline_stages.py:MIN_SEMANTIC_SCORE` and
its consumer in `_score_kwargs_from_settings`. The wire-in replaces:

```python
# Before
"min_semantic_score": MIN_SEMANTIC_SCORE,
```

with:

```python
# After
from apps.pipeline.services.score_calibration import passes_calibrated_threshold
"min_semantic_score_predicate": passes_calibrated_threshold,
```

…and updates `score_destination_matches` to use the predicate.
Deferred until at least one calibration job has run on real feedback
data.

## 8 · Citations on every default

- `MIN_CALIBRATED_PROBABILITY_DEFAULT = 0.5` — Platt 1999 §2 (sigmoid decision boundary).
- `RECALIBRATION_CADENCE_DAYS_DEFAULT = 30` — Guo et al. 2017 ICML §5.
- `VALIDATION_SET_MIN_SIZE_DEFAULT = 1000` — Niculescu-Mizil & Caruana 2005 §4.
- Cold-start `(A=6.0, B=-1.5)` — pragmatic engineering choice; targets `σ(0) = 0.5` at cosine=0.25 to match the historical hardcoded cutoff during the no-fit interim. Will be replaced by a fitted (A, B) on first calibration run.

## 9 · Status

Math + cold-start fallback + tests + spec shipped 2026-05-07. Wire-in into `_apply_min_semantic_score` deferred until first calibration job has labelled validation data ≥1000.
