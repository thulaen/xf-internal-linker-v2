# META-87 — Platt Sigmoid Scaling

## Overview
**Category:** Score calibrator (P9 calibration block)
**Extension file:** `platt_scaling.cpp`
**Replaces/improves:** Raw ranker scores → calibrated probabilities for diagnostics, attribution display, and threshold tuning
**Expected speedup:** ≥8x over `sklearn.linear_model.LogisticRegression` per-call overhead
**RAM:** <2 MB | **Disk:** <1 MB

## Algorithm

```
Input: scores s_i ∈ ℝ, binary labels y_i ∈ {0,1}, i = 1..n
Output: calibrated P(y=1 | s) = 1 / (1 + exp(A·s + B))

Fit by regularised logistic regression on (s, y):
  Use Platt's recommended targets to avoid over-fitting:
    t_+ = (N_+ + 1) / (N_+ + 2)     for positive examples
    t_− = 1     / (N_− + 2)         for negative examples

Minimise:  F(A,B) = − Σ_i [ t_i · log p_i + (1 − t_i) · log(1 − p_i) ]
            where p_i = 1 / (1 + exp(A·s_i + B))

Solve with Newton-Raphson (Hessian-based update, paper Appendix):
  while not converged:
      grad ← [∂F/∂A, ∂F/∂B]
      hess ← [[∂²F/∂A², ∂²F/∂A∂B], [∂²F/∂A∂B, ∂²F/∂B²]]
      step ← solve_2x2(hess, −grad)
      apply line search to ensure F decrease
      (A, B) ← (A, B) + step
```

- **Time complexity:** O(iter · n) per Newton step, typically 10–20 iters
- **Space complexity:** O(n) for cached probabilities
- **Convergence:** Quadratic near optimum (Newton's method)

## Academic source
Platt, J. C., "Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods", in *Advances in Large Margin Classifiers*, MIT Press, 1999.

## C++ Interface (pybind11)

```cpp
// Fit Platt sigmoid; returns (A, B)
std::pair<float, float> platt_fit(
    const float* scores, const int* labels, int n,
    int max_iter = 100, float tol = 1e-7f
);

// Apply Platt calibration in-place
void platt_apply(const float* scores, int n, float A, float B, float* probs_out);
```

## Memory Budget
- Runtime RAM: <2 MB at n=1e6 (one float buffer for cached p_i during fit)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` of size n, reserved at fit start

## Performance Target
- Python baseline: `sklearn.calibration.CalibratedClassifierCV(method='sigmoid')`
- Target: ≥8x faster end-to-end (Newton vs sklearn's iterative LBFGS + boilerplate)
- Benchmark: 3 sizes — n ∈ {1e3, 1e5, 1e6}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate labels ∈ {0,1}.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Sigmoid evaluation vectorised with branch-free clipping.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for log-likelihood reductions. Use numerically stable `log(1 + exp(−x))` via `softplus(−x)` to prevent overflow.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Singular Hessian (degenerate scores) raises ValueError.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_87.py` | (A,B) matches sklearn within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_platt.py` | ≥8x speedup vs sklearn on 3 sizes |
| 5 | `pytest test_edges_meta_87.py` | n=1, all-positive, all-negative, NaN scores, identical scores all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | ECE check | Post-calibration ECE ≤ pre-calibration ECE on test set |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external solver (handwritten 2×2 Newton step)

## Pipeline stage non-conflict declaration
- **Owns:** Two-parameter sigmoid calibration with smoothed Platt targets
- **Alternative to:** META-88 beta calibration (more flexible 3-param), META-89 Dirichlet (multiclass), META-90 histogram binning (non-parametric)
- **Coexists with:** All P8 regularisers (calibration runs after model fit), all P10 LR schedulers (training-time only)

## Test Plan
- Generate synthetic logits with known A,B → verify recovery within 1e-3
- All labels = 1: verify A → ∞, B → −∞ degenerates safely (return clipped probs)
- Identical scores: verify Hessian singularity detected and raises
- Smoothed targets confirmed via paper Eq. — N+ = 1 case yields t+ = 2/3
- Calibration improves Brier score on held-out data
