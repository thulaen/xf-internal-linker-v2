# META-177 — SHAP Values (KernelSHAP)

## Overview
**Category:** Model-agnostic feature attribution (game-theoretic)
**Extension file:** `shap_kernel.cpp`
**Replaces/improves:** `shap.KernelExplainer` Python sampling loop
**Expected speedup:** ≥6x over reference for d=30, 2000 coalition samples
**RAM:** <200 MB | **Disk:** <1 MB

## Algorithm

```
Input: sample x ∈ ℝ^d, background B ⊂ ℝ^{m×d}, model v (payout function)
Output: φ ∈ ℝ^d (one Shapley value per feature)

# Exact Shapley definition
φ_i = Σ_{S ⊆ N\{i}}  ( |S|! · (n − |S| − 1)! / n! ) · ( v(S ∪ {i}) − v(S) )

# KernelSHAP practical estimator
sample coalitions z ∈ {0,1}^d with SHAP kernel weights
  π(z) = (n − 1) / ( C(n, |z|) · |z| · (n − |z|) )
fit weighted linear regression φ = argmin Σ π(z) · (v(h_x(z)) − φ₀ − ⟨z, φ⟩)²
  subject to  Σ φ_i = v(x) − v(∅)     # completeness
```

- **Time complexity:** O(n_samples · eval_cost + d³) for the linear solve
- **Space complexity:** O(n_samples · d)
- **Convergence:** Consistent estimate as n_samples → ∞; satisfies completeness by construction

## Academic Source
Lundberg S.M., Lee S.-I., "A unified approach to interpreting model predictions," *Advances in Neural Information Processing Systems 30 (NIPS 2017)*, pp. 4765–4774. DOI: 10.48550/arXiv.1705.07874

## C++ Interface (pybind11)

```cpp
// KernelSHAP with user-supplied model callback
void shap_kernel(
    const float* x, int d,
    const float* background, int m,
    std::function<float(const float*, int)> model,
    int n_coalition_samples, uint64_t seed,
    float* out_phi, float* out_phi0
);
```

## Memory Budget
- Runtime RAM: <200 MB for d=30, 2000 coalitions (coalition matrix + weights)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed coalition matrix; `reserve()` up-front

## Performance Target
- Python baseline: `shap.KernelExplainer`
- Target: ≥6x faster for d=30, 2000 coalitions
- Benchmark: d ∈ {10, 30, 100}, samples ∈ {500, 2000, 10000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Coalition evaluations parallelised; each worker gets its own PRNG via `seed_seq`. Model callback must be thread-safe.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. Guard d² and d³ allocations against budget.

**Object lifetime:** Self-assignment safe. No dangling capture of `background` in callbacks.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on feature indices.

**SIMD:** AVX2 FMA for the weighted least-squares normal equations. `_mm256_zeroupper()` at epilogue. `alignas(64)` on design matrix.

**Floating point:** Flush-to-zero on init. NaN/Inf checks on x and model outputs. Double accumulator for WLS normal equations; regularise with tiny ridge if near-singular.

**Performance:** No `std::endl` loops. `std::function` explicitly permitted here for model callback with justification. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Reject d<1, m<1.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory. PRNG seed logged but not exposed.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_177.py` | Matches `shap.KernelExplainer` within 5% per feature at 10k samples |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than reference |
| 5 | `pytest test_edges_meta_177.py` | Constant model, linear model, single feature, completeness check |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in parallel evaluations |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (user-provided model callback)

## Pipeline Stage Non-Conflict
- **Owns:** Game-theoretic local feature attribution with completeness guarantee.
- **Alternative to:** META-176 (permutation), META-178 (LIME), META-179 (integrated gradients).
- **Coexists with:** Diagnostics dashboard; ranking output is unchanged — SHAP explains per-candidate scores.
- No conflict with ranking: runs offline or on-demand for explanations only.

## Test Plan
- Linear model: φ_i exactly equals coefficient · (x_i − x̄_i) within FP tolerance
- Completeness: verify Σ φ_i + φ₀ ≈ v(x) within 1e-4
- Constant model: verify all φ = 0
- Single-feature model: verify φ recovers the marginal effect
- NaN model output: verify raises ValueError
