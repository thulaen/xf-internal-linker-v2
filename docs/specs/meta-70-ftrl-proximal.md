# META-70 — FTRL-Proximal Online Learner

## Overview
**Category:** Online learner (Follow-the-Regularised-Leader, sparse linear models)
**Extension file:** `ftrl_proximal.cpp`
**Replaces/improves:** META-34 Adam / META-35 SGD-momentum for streaming click-through learning where exact L1 sparsity is required (e.g. linker quality model with millions of features but only a few thousand active per request)
**Expected speedup:** ≥10x over `tensorflow_addons.optimizers.FTRL` per-step
**RAM:** <50 MB (sparse storage) | **Disk:** <1 MB

## Algorithm
```
Input: feature vector x_t (sparse), gradient g_t = ∇L(w_t · x_t, y_t),
       per-coordinate learning rate α, β, L1 λ_1, L2 λ_2
Output: updated weights w_{t+1}

# Per-coordinate accumulators z_i, n_i (n_i = Σ g_i², z_i = ‘virtual gradient sum’)
for each i with g_{t,i} ≠ 0:                                          # McMahan et al. 2013 §3.1
    σ_i = (sqrt(n_i + g_{t,i}²) − sqrt(n_i)) / α
    z_i ← z_i + g_{t,i} − σ_i · w_{t,i}
    n_i ← n_i + g_{t,i}²

# Closed-form weight update (handles L1 exactly via soft-threshold):
for each i:
    if |z_i| ≤ λ_1: w_{t+1,i} = 0
    else:           w_{t+1,i} = − (z_i − sign(z_i)·λ_1) / ((β + sqrt(n_i))/α + λ_2)
```
- Time complexity: O(|active features| ) per step
- Space complexity: O(|all features ever seen|) for z, n
- Regret: O(√T) sublinear (McMahan 2011 Thm 1)

## Academic source
**McMahan, H. B., Holt, G., Sculley, D., Young, M., Ebner, D., Grady, J., Nie, L., Phillips, T., Davydov, E., Golovin, D., Chikkerur, S., Liu, D., Wattenberg, M., Hrafnkelsson, A. M., Boulos, T., Kubica, J. (2013).** "Ad click prediction: a view from the trenches." *Proc. 19th ACM SIGKDD*, pp. 1222-1230. DOI: `10.1145/2487575.2488200`.

## C++ Interface (pybind11)
```cpp
// Sparse FTRL step; weight vector represented as a hash map
struct FTRLState {
    absl::flat_hash_map<uint64_t, float> z, n;
    float alpha, beta, lambda1, lambda2;
};

void ftrl_step(
    FTRLState& s,
    const uint64_t* feature_ids, const float* feature_vals, int n_active,
    float gradient_scalar      // dL/d(w·x), e.g. (sigmoid(p) − y) for log-loss
);

void ftrl_predict(
    const FTRLState& s,
    const uint64_t* feature_ids, const float* feature_vals, int n_active,
    float* out_score
);
```

## Memory budget
- Runtime RAM: <50 MB (1M sparse features × (z, n) = 8 bytes each + 8-byte hash key + 8-byte overhead → ~24 MB nominal, 50 MB cap with growth slack)
- Disk: <1 MB compiled
- Allocation: `absl::flat_hash_map` with `reserve()` at construction; per-step has zero heap allocation if reserve held

## Performance target
- Python baseline: `tensorflow_addons.optimizers.FTRL` Python wrapper
- Target: ≥10x faster per step (no TF graph compile overhead, hash map vs dense weight tensor)
- Benchmark: stream of 1M (sparse_x, y) pairs, 50 active features per step

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in step kernel, NaN/Inf checks on gradient (NaN → no-op, log warning via callback), double accumulator for σ_i sqrt-difference (sqrt(n+g²)−sqrt(n) suffers catastrophic cancellation when g² ≪ n — use the algebraically-equivalent `g²/(sqrt(n+g²)+sqrt(n))` form), `noexcept` destructors, no `std::function` in step kernel, hash-map `reserve()` at construction (no rehash mid-stream), L1 soft-threshold uses `std::copysign`, predict and step share a single hash-map lookup pass, no exceptions in predict (return 0 for missing keys).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_70.py` | Final weights match TF FTRL within 1e-5 over 10k steps |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥10x faster per step |
| 5 | Edge cases | g=0, λ_1=0 (no sparsity), λ_1=∞ (all zero), feature seen once, NaN gradient pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (state mutated under caller-held lock; document) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- `absl::flat_hash_map` (vendored under `third_party/abseil`)
- META-34 Adam loss-callback signature (re-used for log-loss / pairwise gradient)

## Pipeline stage (non-conflict)
**Owns:** sparse online linear-model optimiser slot (L1 + L2 with per-coordinate rate)
**Alternative to:** META-71 ONS (dense, O(d²)), META-72 OMD (dense, mirror-descent), META-74 projected OGD (dense, no L1)
**Coexists with:** META-25 sliding-window retrainer (offline batch), META-04 coordinate ascent (offline)

## Test plan
- Synthetic logistic regression on 100k sparse rows: matches scikit-learn weights within 1e-3
- λ_1=0 (no L1): all coordinates non-zero, regret matches OGD reference
- λ_1=10 (heavy L1): final weight density ≤ 5% of features
- NaN gradient: state unchanged, warning emitted
- 10M-step stream, 50 active features per step: completes within target wall-clock budget
