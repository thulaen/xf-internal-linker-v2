# META-178 — LIME (Local Interpretable Model-agnostic Explanations)

## Overview
**Category:** Model-agnostic local surrogate attribution
**Extension file:** `lime.cpp`
**Replaces/improves:** `lime` Python package local sampling loop
**Expected speedup:** ≥5x over `lime.lime_tabular` for d=30, 5k perturbations
**RAM:** <150 MB | **Disk:** <1 MB

## Algorithm

```
Input: sample x ∈ ℝ^d, black-box f, proximity kernel π_x, surrogate family G
Output: g ∈ G with interpretable coefficients

sample Z = { z_k ~ perturb(x) }  (binary/continuous)
weights w_k = π_x(z_k) = exp( −D(x, z_k)² / σ² )
labels  y_k = f(h_x(z_k))     # h_x maps z back to original feature space

g = argmin_{g ∈ G}  Σ_k w_k · L( y_k, g(z_k) )  +  Ω(g)

typical G = sparse linear model (Lasso), Ω(g) = λ·||β||₁
```

- **Time complexity:** O(n_samples · eval_cost + d²) for Lasso fit
- **Space complexity:** O(n_samples · d)
- **Convergence:** Depends on surrogate; for Lasso, coordinate descent is monotone and convex

## Academic Source
Ribeiro M.T., Singh S., Guestrin C., "'Why Should I Trust You?': Explaining the predictions of any classifier," *Proc. KDD 2016*, pp. 1135–1144. DOI: 10.1145/2939672.2939778

## C++ Interface (pybind11)

```cpp
// LIME tabular explainer using Lasso as the surrogate family
void lime_tabular(
    const float* x, int d,
    std::function<float(const float*, int)> model,
    int n_samples, float kernel_width, float lasso_alpha,
    uint64_t seed,
    float* out_coefs, float* out_intercept, float* out_r2
);
```

## Memory Budget
- Runtime RAM: <150 MB for d=30, 5k perturbations
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: one `std::vector<float>` for Z (n×d) and one for weights and labels, `reserve()` up-front

## Performance Target
- Python baseline: `lime.lime_tabular.LimeTabularExplainer`
- Target: ≥5x faster for d=30, 5k perturbations
- Benchmark: d ∈ {10, 30, 100}, samples ∈ {1k, 5k, 20k}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Perturbation evaluation parallelised; per-thread PRNG via `seed_seq`. Model callback must be thread-safe.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling capture of x in callbacks.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on feature indices.

**SIMD:** AVX2 FMA for Lasso coordinate-descent inner products. `_mm256_zeroupper()` at epilogue. `alignas(64)` on Z matrix rows.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on x and f outputs. Gaussian kernel guarded against σ=0. Double accumulator for weighted residual sums.

**Performance:** No `std::endl` loops. `std::function` explicitly permitted for the model callback with justification comment. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject kernel_width≤0, alpha<0.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory. PRNG seed logged but not exposed.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_178.py` | Coefficient sign agreement ≥95% with `lime` package on linear models |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than `lime` |
| 5 | `pytest test_edges_meta_178.py` | Constant f, d=1, alpha=0 (OLS), alpha huge (all-zero) handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (user-provided model callback)

## Pipeline Stage Non-Conflict
- **Owns:** Local surrogate explanation of a single prediction in interpretable feature space.
- **Alternative to:** META-176 (permutation), META-177 (SHAP), META-179 (integrated gradients).
- **Coexists with:** Diagnostics UI for "explain this recommendation" per-row drill-down.
- No conflict with ranking: runs on-demand for explanation; ranker output unchanged.

## Test Plan
- Linear ground-truth model: LIME coefs highly correlated with true coefs (ρ ≥ 0.9)
- Kernel-width sensitivity: verify smooth degradation as width → ∞
- Zero perturbations: verify raises ValueError
- Constant f: verify coefs = 0, R² = 0 (documented)
- NaN in x: verify raises ValueError
