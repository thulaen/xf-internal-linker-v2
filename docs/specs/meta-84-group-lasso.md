# META-84 — Group LASSO

## Overview
**Category:** Structured-sparsity regulariser (P8 regularisation block)
**Extension file:** `group_lasso.cpp`
**Replaces/improves:** Element-wise L1 in feature-group selection — drives entire feature groups to zero, useful for embedding-block, n-gram-block, or per-section weight pruning
**Expected speedup:** ≥6x over Python per-group prox loop
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm

```
Input: feature matrix X ∈ ℝ^{n×p}, target y ∈ ℝ^n,
       group partition G = {G_1, …, G_K} of {1..p},
       group weights p_g (= |G_g| or √|G_g|), λ > 0
Output: β* = argmin (1/2)·‖y − Xβ‖² + λ·Σ_g √p_g · ‖β_g‖₂

Block-coordinate prox:
    β_g ← prox_{ηλ√p_g · ‖·‖₂}( β_g − η · X_gᵀ (Xβ − y) )
        = max(1 − ηλ√p_g / ‖v_g‖₂, 0) · v_g       (block soft-threshold)

repeat:
    for g = 1..K:
        v_g  ← β_g − η · X_gᵀ · r        // r = Xβ − y, kept incrementally
        β_g  ← block_soft_threshold(v_g, η·λ·√p_g)
        r    ← r + X_g · (β_g_new − β_g_old)
until ‖β_new − β_prev‖₂ < tol
```

- **Time complexity:** O(iter · n · p) per pass; block step is O(n · |G_g|)
- **Space complexity:** O(p + n) (β + residual r)
- **Convergence:** Block-coordinate descent, linear rate under restricted-strong-convexity

## Academic source
Yuan, M. and Lin, Y., "Model Selection and Estimation in Regression with Grouped Variables", *Journal of the Royal Statistical Society: Series B (Statistical Methodology)*, 68(1):49–67, 2006. DOI 10.1111/j.1467-9868.2005.00532.x.

## C++ Interface (pybind11)

```cpp
// Block-coordinate descent for group LASSO
std::vector<float> group_lasso_fit(
    const float* X, int n, int p,        // row-major
    const float* y,
    const int* group_id, int n_groups,   // group_id[j] ∈ [0, n_groups)
    const float* group_weights,          // length n_groups
    float lambda, float step, float tol, int max_iter
);
```

## Memory Budget
- Runtime RAM: <12 MB at p=10000, n=10000 (β + residual + per-group cached column-norms)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized `std::vector<float>` for β and r, group offsets cached at fit start

## Performance Target
- Python baseline: `sklearn.linear_model.MultiTaskLasso` (analogous, group-wise)
- Target: ≥6x faster on n=p=1000, K=50 groups
- Benchmark: 3 sizes — (n,p,K) ∈ {(100,50,10), (1000,500,50), (10000,5000,200)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Group-index lookup table built once at fit start.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Group IDs validated to be in `[0, n_groups)`.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Per-group dot product vectorised when group size ≥ 8.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for `‖v_g‖₂` reductions when group size > 100.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Residual `r` updated incrementally — never recomputed from scratch.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_84.py` | Matches Python reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_group_lasso.py` | ≥6x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_84.py` | K=1, K=p (degenerates to L1), empty group, all-zero y handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Sparsity check | At fixed λ, # active groups matches reference within ±1 |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- META-82 FISTA (optional outer accelerator)
- pybind11 ≥ 2.10

## Pipeline stage non-conflict declaration
- **Owns:** Group block-soft-threshold prox + block-coordinate solver
- **Alternative to:** Element-wise L1 (LASSO) when groups are meaningful (sections, n-gram blocks, embedding chunks)
- **Coexists with:** META-82 FISTA, META-83 nuclear norm, META-85 fused LASSO, META-86 SCAD; all are independent regularisers and can be combined linearly via Σ λ_k · h_k(β)

## Test Plan
- Synthetic data with 5 of 50 groups truly nonzero: verify only those groups recovered
- K=1 (one global group) reduces to ridge with √p shrinkage
- K=p (each feature its own group) reduces to plain L1 — verify parity with FISTA-LASSO
- Group with all-zero column: verify β_g stays at 0
- Verify monotonic objective decrease per outer iter
