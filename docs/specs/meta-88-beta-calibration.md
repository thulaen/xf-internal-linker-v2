# META-88 — Beta Calibration

## Overview
**Category:** Score calibrator (P9 calibration block)
**Extension file:** `beta_calibration.cpp`
**Replaces/improves:** Platt sigmoid (META-87) when calibration map is asymmetric — beta calibration's 3-parameter family handles boundary asymmetry (extreme low and extreme high scores miscalibrated differently)
**Expected speedup:** ≥6x over Python LBFGS-based fit
**RAM:** <2 MB | **Disk:** <1 MB

## Algorithm

```
Input: scores s_i ∈ (0,1), labels y_i ∈ {0,1}, n samples
Output: calibrated P(y=1 | s) using 3-parameter beta family

Map (paper Eq. 5):
  P(y=1 | s) = 1 / (1 + exp(−( a · log(s) − b · log(1 − s) + c )))
  where a, b ≥ 0, c ∈ ℝ

Equivalent reparameterisation as logistic regression on transformed features:
  ψ(s) = [ log(s),  −log(1 − s) ]
  Fit logistic regression with coefficients (a, b) and intercept c,
  with non-negativity constraints a ≥ 0, b ≥ 0 (active-set or projected Newton).

Newton-with-projection:
  while not converged:
      grad ← ∂NLL/∂(a,b,c)
      hess ← 3×3 Hessian
      step ← solve_3x3(hess, −grad)
      (a,b,c) ← (a,b,c) + step
      project a ← max(a, 0); b ← max(b, 0)
```

- **Time complexity:** O(iter · n) per Newton step, ~15 iters typical
- **Space complexity:** O(n) cached probabilities + 3×3 Hessian
- **Convergence:** Quadratic near optimum; projection breaks at boundary but converges in finite steps

## Academic source
Kull, M., Silva Filho, T. and Flach, P., "Beta Calibration: A Well-Founded and Easily Implemented Improvement on Logistic Calibration for Binary Classifiers", *Proceedings of the 20th International Conference on Artificial Intelligence and Statistics (AISTATS)*, PMLR 54:623–631, 2017.

## C++ Interface (pybind11)

```cpp
// Fit beta calibration; returns (a, b, c)
std::tuple<float, float, float> beta_fit(
    const float* scores, const int* labels, int n,
    int max_iter = 100, float tol = 1e-7f
);

// Apply beta calibration
void beta_apply(
    const float* scores, int n,
    float a, float b, float c,
    float* probs_out
);
```

## Memory Budget
- Runtime RAM: <2 MB at n=1e6 (one buffer for log(s), one for log(1−s))
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; logs computed once at fit start

## Performance Target
- Python baseline: `betacal` PyPI package
- Target: ≥6x faster on n=1e5
- Benchmark: 3 sizes — n ∈ {1e3, 1e5, 1e6}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate scores ∈ (0,1); clamp to (ε, 1−ε) at entry.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. log + sigmoid vectorised with branch-free clipping.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for log-likelihood reductions. Use stable `softplus` for sigmoid log-likelihood.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Score = 0 or 1 raises (would yield log(-∞)).

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_88.py` | (a,b,c) matches `betacal` within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_beta.py` | ≥6x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_88.py` | scores at boundary, all-positive, all-negative, n=1, projection active set all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Asymmetric calib | On synthetic asymmetric miscalibration, beta beats Platt's ECE |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-87 Platt scaling (collapses to Platt when a = b)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** 3-parameter beta calibration with non-negativity projection
- **Alternative to:** META-87 Platt (less flexible), META-90 histogram (non-parametric)
- **Coexists with:** META-89 Dirichlet (multiclass — beta is binary), all P8 regularisers, all P10 schedulers

## Test Plan
- Synthetic data with known a,b,c: verify recovery within 1e-3
- a = b = 1, c = 0: verify reduces to identity (no calibration)
- a = b: verify reduces to Platt sigmoid scaling — parity with META-87
- Constraint hit: random init forcing a < 0 — verify projection moves to a = 0 cleanly
- Boundary scores 0/1: verify clamped or rejected with clear error
