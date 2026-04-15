# META-179 — Integrated Gradients

## Overview
**Category:** Gradient-based feature attribution (differentiable models)
**Extension file:** `integrated_gradients.cpp`
**Replaces/improves:** Python IG loop in `xai.py` calling torch.autograd
**Expected speedup:** ≥4x over Python loop (mainly overhead reduction around autograd calls)
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

```
Input: input x ∈ ℝ^d, baseline x' ∈ ℝ^d, differentiable model f, m steps
Output: attributions IG ∈ ℝ^d

# Riemann-midpoint approximation of the path integral
IG_i(x) = (x_i − x'_i) · ∫₀¹ ( ∂f( x' + α·(x − x') ) / ∂x_i ) dα

approximation:
for k = 1..m:
    α_k = (k − 0.5) / m
    ∇_k = ∇_x f(x' + α_k · (x − x'))
IG ≈ (x − x') · ( 1/m · Σ_k ∇_k )

# completeness axiom
Σ_i IG_i ≈ f(x) − f(x')   (within discretisation error)
```

- **Time complexity:** O(m · grad_cost)
- **Space complexity:** O(d + model activations)
- **Convergence:** Riemann error O(1/m) for smooth f; satisfies sensitivity, implementation invariance, and completeness

## Academic Source
Sundararajan M., Taly A., Yan Q., "Axiomatic attribution for deep networks," *Proc. 34th International Conference on Machine Learning (ICML 2017)*, PMLR 70:3319–3328. DOI: 10.48550/arXiv.1703.01365

## C++ Interface (pybind11)

```cpp
// Integrated Gradients with user-supplied gradient callback
void integrated_gradients(
    const float* x, const float* baseline, int d,
    std::function<void(const float*, int, float*)> grad_callback,
    int n_steps,
    float* out_ig, float* out_completeness_gap
);
```

## Memory Budget
- Runtime RAM: <80 MB for d=1024, n_steps=50
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: two `std::vector<float>` (interpolated x, accumulated grad), `reserve(d)` up-front

## Performance Target
- Python baseline: Hand-written IG loop in `xai.py`
- Target: ≥4x faster for d=1024, n_steps=50
- Benchmark: d ∈ {64, 1024, 4096}, n_steps ∈ {20, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Steps are serial (the gradient callback typically holds the GPU); parallelism happens inside the callback, not here.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve(d)` before fills.

**Object lifetime:** Self-assignment safe. No dangling capture of baseline/x in callback.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** AVX2 FMA for the `(x − x') · (Σ ∇_k / m)` reduction. `_mm256_zeroupper()` at epilogue. `alignas(64)` on interpolation buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on x, baseline, gradients. Double accumulator for Σ ∇_k. Report completeness gap = `f(x) − f(x') − Σ IG_i` for diagnostics.

**Performance:** No `std::endl` loops. `std::function` permitted for gradient callback with justification comment. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject n_steps<1.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_179.py` | Matches reference Python IG within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_179.py` | Zero baseline, x=x' (IG must be 0), large n_steps handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (serial algorithm; TSAN still run) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (user-provided gradient callback)

## Pipeline Stage Non-Conflict
- **Owns:** Gradient-integrated attribution for the differentiable reranker (META-scale transformer).
- **Alternative to:** META-176 (permutation), META-177 (SHAP), META-178 (LIME).
- **Coexists with:** SHAP for non-differentiable components and permutation for sanity checks.
- No conflict with ranking: attributions are offline; ranker output unchanged.

## Test Plan
- Linear f: verify IG_i = (x_i − x'_i) · w_i exactly (within FP tol)
- x = baseline: verify IG = 0 and completeness gap = 0
- ReLU net: verify completeness gap shrinks as n_steps grows (≤0.01 at n_steps=200)
- NaN gradient: verify raises ValueError
- Very high d=4096: verify runtime budget respected
