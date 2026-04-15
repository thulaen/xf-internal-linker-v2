# META-85 — Fused LASSO

## Overview
**Category:** Smoothness + sparsity regulariser (P8 regularisation block)
**Extension file:** `fused_lasso.cpp`
**Replaces/improves:** Independent feature selection — encourages adjacent feature weights (e.g. positional embedding bins, ordered importance buckets) to share values
**Expected speedup:** ≥5x over Python ADMM solver
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×p}, y ∈ ℝ^n, λ₁ (sparsity), λ₂ (fusion)
Output: β* = argmin (1/2)·‖y − Xβ‖² + λ₁·‖β‖₁ + λ₂·Σ_{i=2..p} |β_i − β_{i−1}|

Solve via dual or direct path algorithm:
  Step A: total-variation prox via taut-string / Condat O(p) algorithm
          β_TV ← TV_prox(z, λ₂) where z = β − η·∇g(β)
  Step B: soft-threshold for L1
          β    ← sign(β_TV) · max(|β_TV| − η·λ₁, 0)

repeat until ‖β_new − β_prev‖₂ < tol:
    z   ← β − η · Xᵀ(Xβ − y)
    β   ← soft_threshold( TV_prox_1d(z, η·λ₂), η·λ₁ )
```

- **Time complexity:** O(iter · (n·p + p)); TV prox is O(p) via Condat
- **Space complexity:** O(p + n)
- **Convergence:** Sub-linear; combine with FISTA momentum (META-82) for O(1/t²)

## Academic source
Tibshirani, R., Saunders, M., Rosset, S., Zhu, J. and Knight, K., "Sparsity and Smoothness via the Fused Lasso", *Journal of the Royal Statistical Society: Series B (Statistical Methodology)*, 67(1):91–108, 2005. DOI 10.1111/j.1467-9868.2005.00490.x.

## C++ Interface (pybind11)

```cpp
// 1-D total-variation proximal operator (Condat O(p))
void tv_prox_1d(const float* z, int p, float lambda, float* out);

// Full fused-LASSO fit
std::vector<float> fused_lasso_fit(
    const float* X, int n, int p,
    const float* y,
    float lambda1, float lambda2,
    float step, float tol, int max_iter
);
```

## Memory Budget
- Runtime RAM: <8 MB at p=50000 (β + residual + TV stack)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized stack vectors for Condat algorithm, no per-iter alloc

## Performance Target
- Python baseline: ADMM with NumPy `np.diff` + iterative solver
- Target: ≥5x faster on p=10000
- Benchmark: 3 sizes — p ∈ {100, 10000, 100000} with n=p

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Condat stack pre-allocated to size p.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Note: Condat is inherently scalar (carry-state) — vectorise only the soft-threshold pass.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for residual reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_85.py` | Matches `cvxpy` reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_fused.py` | ≥5x faster than ADMM baseline on 3 sizes |
| 5 | `pytest test_edges_meta_85.py` | p=1, λ₁=0, λ₂=0, λ₂=∞ (constant β) all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | TV prop check | After fit, # distinct β values ≤ expected piecewise-constant count |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-82 FISTA (composes for momentum)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** 1-D TV prox (Condat) + fused-LASSO outer loop
- **Alternative to:** Plain LASSO when feature ordering carries meaning (positional, temporal, ordered bins)
- **Coexists with:** META-82 FISTA, META-83 nuclear norm, META-84 group LASSO, META-86 SCAD; combinable as additive penalty

## Test Plan
- Piecewise-constant ground truth: verify recovered β is piecewise constant
- λ₂ = 0 reduces to LASSO — parity with META-82 + L1
- λ₁ = 0 reduces to fused signal estimator
- p = 1: degenerate, returns soft-threshold of single coordinate
- Monotonically decreasing objective verified across outer iterations
