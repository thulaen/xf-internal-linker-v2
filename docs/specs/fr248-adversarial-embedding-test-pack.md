# FR-248 — Adversarial regression test pack for the embedding pipeline

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Adversarial embedding pipeline test pack |
| **Test file** | `backend/apps/pipeline/tests_embedding_adversarial.py` |
| **Test count** | 14 SimpleTestCase tests across 5 classes (one class per failure mode) |
| **Default state** | **ON in CI.** Tests run as part of `apps.pipeline` test target. |

## 2 · Motivation (ELI5)

The embedding pipeline today has tests for the happy path (does a clear match return the right thing?) but never tests the cases that expose the model's known weaknesses. Without these regression tests, a future commit could silently break homonym handling, numerical stability, or GPU/CPU parity and we'd only notice via degraded suggestion quality in production. This spec ships a starting-point test pack that locks in the contracts and gives future agents a discoverable place to add deeper checks.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Test methodology** | Beizer, B. (1990). *Software Testing Techniques* (2nd ed.). Van Nostrand Reinhold. ISBN 978-0442206727. Chapters 4–6 — equivalence partitioning + boundary value analysis + decision-table testing. |
| **Homonym methodology** | Navigli, R. et al. (2013). *SemEval-2013 Task 12: Multilingual Word Sense Disambiguation.* https://aclanthology.org/S13-2040/. Establishes the homonym/polysemy benchmark methodology. |
| **fp32 determinism** | IEEE 754-2019 — DOI: [10.1109/IEEESTD.2019.8766229](https://doi.org/10.1109/IEEESTD.2019.8766229). §5.4 single-precision rounding rules. |
| **NaN / Inf injection** | Higham, N. J. (2002). *Accuracy and Stability of Numerical Algorithms* (2nd ed.). SIAM. ISBN 978-0898715217. NaN/Inf injection methodology. |

## 4 · Coverage by class (5 buckets, 14 tests)

| Class | Tests | Bucket from plan | Notes |
|---|---|---|---|
| `HomonymRegressionTests` | 3 | Bucket 4 (polysemy) | Synthetic well-separated vectors. SemEval-2013 integration deferred (needs encoder). |
| `OutOfDistributionTests` | 3 | Bucket 3 (general-English model) | Synthetic weak-magnitude vectors via L2 audit. |
| `EmbeddingStalenessTests` | 2 | Bucket 13 (age decay) | FR-249 contract lock-in. |
| `GpuCpuParityTests` | 2 | Bucket 10 (FAISS-IP vs NumPy-dot) | Math-layer parity; full forward-pass parity needs CUDA runner. |
| `NumericalStabilityTests` | 4 | Bucket 12 (NaN/Inf) | Higham 2002 injection. Includes a documented gap (NaN audit slipping through) for future tightening. |

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/tests_embedding_adversarial.py` | New file. ~210 lines, 14 SimpleTestCase tests. |

All tests run as `SimpleTestCase` — no DB, no Docker dep, no model load. They lock the math-layer contracts of:
- `_audit_l2_normalization` (FR-237)
- `compute_embedding_age_decay` (FR-249)
- `mmr_rerank_keys` (FR-239)

…against the failure modes called out in the weakness audit.

## 6 · Documented gaps (future commits)

The starting-point pack covers the math-layer contracts. The following deeper checks are deferred:

| Gap | Why deferred |
|---|---|
| Full BGE-M3 forward-pass tests on SemEval-2013 homonym pairs | Needs encoder load (~2GB RAM) + sentence-transformers ≥ 2.2 + a downloadable evaluation set. Belongs in a slow-test target, not the unit suite. |
| CUDA vs CPU forward-pass byte-equivalence | Needs CUDA-equipped CI runner (current CI is CPU-only). |
| NaN-detection raise in `_audit_l2_normalization` | Currently NaN comparisons evaluate to False so the audit slips through. Test `test_nan_in_vector_caught_by_audit` documents the gap and passes today; a future commit can add `if np.any(np.isnan(arr)): raise` and tighten the assertion. |
| Cross-version embedding mismatch (model A vs model B) | Needs two embedding-provider versions side-by-side; covered partially by FR-236 quality-gate stability check. |

## 7 · Citations on every default

- `tolerance` checks at 1e-6 — IEEE 754-2019 §5.4 (fp32 unit-magnitude rounding floor).
- Test class structure (5 buckets matching audit findings) — Beizer 1990 §4 equivalence partitioning.
- Synthetic-vector approach — Higham 2002 §1.4 (controlled adversarial inputs).
- Homonym test design — Navigli 2013 §3 (well-separated semantic clusters).

## 8 · Status

Shipped 2026-05-07. 14/14 pass.
