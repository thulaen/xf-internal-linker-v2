# META-89 — Dirichlet Calibration

## Overview
**Category:** Multiclass score calibrator (P9 calibration block)
**Extension file:** `dirichlet_calibration.cpp`
**Replaces/improves:** Per-class one-vs-rest Platt sigmoid for multiclass intent buckets (when relevance is bucketed into K>2 strata). Maintains class-probability simplex consistency that one-vs-rest cannot guarantee.
**Expected speedup:** ≥5x over Python reference fit
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: probability vectors s_i ∈ Δ^{K-1}, labels y_i ∈ {1..K}, n samples
Output: calibrated P(y | s) via Dirichlet-family generative model

Generative model (paper Section 3):
  P(y = k | s) ∝ exp( w_kᵀ · log(s) + b_k )
  i.e. log-domain linear map followed by softmax.
  Equivalent matrix form:
    P(y | s) = softmax(W · log(s) + b),  W ∈ ℝ^{K×K}, b ∈ ℝ^K

Fit by multinomial logistic regression on transformed features ψ(s) = log(s):
  Optimise NLL with L2 regularisation (paper recommends λ chosen by CV) via
  Newton or LBFGS:
      F(W,b) = − Σ_i log P(y_i | s_i) + (λ/2)·‖W − I‖_F²

(Off-diagonal regularisation toward identity preserves uncalibrated solution
 as the prior, which is the paper's recommendation for stable fitting.)
```

- **Time complexity:** O(iter · n · K²)
- **Space complexity:** O(K² + n·K) for cached log-probs
- **Convergence:** Newton converges quadratically in 10–25 iters

## Academic source
Kull, M., Perelló-Nieto, M., Kängsepp, M., Silva Filho, T., Song, H. and Flach, P., "Beyond Temperature Scaling: Obtaining Well-Calibrated Multi-class Probabilities with Dirichlet Calibration", *Advances in Neural Information Processing Systems (NeurIPS)*, 2019.

## C++ Interface (pybind11)

```cpp
// Fit Dirichlet calibration; returns flattened (W ∈ ℝ^{K×K}, b ∈ ℝ^K)
std::pair<std::vector<float>, std::vector<float>> dirichlet_fit(
    const float* probs, const int* labels, int n, int K,
    float l2_reg, int max_iter = 100, float tol = 1e-6f
);

// Apply Dirichlet calibration in-place (probs_in → probs_out)
void dirichlet_apply(
    const float* probs_in, int n, int K,
    const float* W, const float* b,
    float* probs_out
);
```

## Memory Budget
- Runtime RAM: <8 MB at K=10, n=1e5 (log-prob cache + Hessian K²×K²)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; log(s) computed once

## Performance Target
- Python baseline: paper-author reference impl in NumPy
- Target: ≥5x faster on K=5, n=1e5
- Benchmark: 3 sizes — (n,K) ∈ {(1e3,3), (1e5,5), (1e6,10)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate probs ∈ Δ^{K-1} (sum to 1, all > 0).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Softmax + log vectorised.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for NLL reductions. Numerically stable softmax with max-subtraction.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. probs containing 0 raises (log(0) undefined); accept ε-floor as option.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_89.py` | (W,b) matches author reference within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_dirichlet.py` | ≥5x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_89.py` | K=2 (degenerates), K=1 (raises), n=1, simplex violation handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Multiclass ECE | Post-calibration multiclass ECE ≤ pre-calibration on test set |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-87 Platt (parity check at K=2 with W=diag, b=0 baseline)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Multiclass log-domain linear → softmax calibrator
- **Alternative to:** Per-class one-vs-rest Platt, temperature scaling
- **Coexists with:** META-87 (binary case), META-88 (binary asymmetric), META-90 (binary non-parametric); for binary problems use Platt/Beta/Histogram instead

## Test Plan
- W = I, b = 0 init: verify produces identity calibration on first iter
- K = 2: results within 1e-3 of META-87 Platt on same data
- Synthetic miscalibrated multiclass logits: verify ECE drops
- All examples one class: degenerate fit handled (warn but succeed with high regularisation)
- Output sums to 1 across all rows (simplex preservation)
