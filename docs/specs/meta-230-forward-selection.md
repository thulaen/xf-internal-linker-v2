# META-230 — Forward Selection

## Overview
**Category:** Feature selection (wrapper, sequential)
**Extension file:** `forward_select.cpp`
**Replaces/improves:** sklearn `SequentialFeatureSelector(direction='forward')` Python loop
**Expected speedup:** ≥5x over Python reference
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

Start with empty set; at each step add the feature that most improves a validation metric (Efroymson 1960).

```
Input: X ∈ ℝ^{n×d}, y, validation splitter CV, metric (e.g. NDCG or AUC), max_k, tol
Output: ordered selected set S

S ← ∅
prev_score ← −∞
for step = 1..max_k:
    best_f ← none
    best_score ← −∞
    for each candidate f ∈ F \ S:
        model ← fit_linear_or_gbm(X[:, S ∪ {f}], y) with CV
        score ← metric(model, held-out folds)
        if score > best_score:
            best_f ← f
            best_score ← score
    if best_score − prev_score < tol:
        break                                         (no improvement → stop)
    S ← S ∪ {best_f}
    prev_score ← best_score
return S
```

- **Time complexity:** O(k · d · fit_cost) — k iterations × d candidates × CV fit
- **Space complexity:** O(n·d) for X + O(k) for selected list
- **Convergence:** Greedy — terminates when marginal gain < tol or |S|=max_k

## C++ Interface (pybind11)

```cpp
// Forward selection with CV; returns features in selection order + scores
struct ForwardOut {
    std::vector<int> selected;
    std::vector<float> cv_scores;
};

ForwardOut forward_select(
    const float* X, int n, int d,
    const float* y,
    int max_k, float improvement_tol,
    int num_cv_folds, float ridge_lambda,
    unsigned seed
);
```

## Memory Budget
- Runtime RAM: <30 MB (X view + CV fold residuals + warm-start state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(max_k + n * max_k)`

## Performance Target
- Python baseline: sklearn `SequentialFeatureSelector` (Python loop over fits)
- Target: ≥5x faster (warm-start per added feature, parallel candidate evaluation)
- Benchmark: n=10k × d ∈ {50, 200, 1000} × max_k ∈ {10, 30}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across candidate features within each iteration; no shared mutable state in candidate fits. CV fold splits pre-computed once.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for CV score averaging. Ridge regularization to avoid singular normal equations.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. Explicit RNG seed for CV split — no `rand()`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_230.py` | Selection order matches sklearn with same seed and CV |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than sklearn reference |
| 5 | `pytest test_edges_meta_230.py` | max_k=d, max_k=1, constant feature, collinear pair pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across candidate-fit threads |
| 8 | Human reviewer | CPP-RULES.md compliance + CV-leakage audit |

## Dependencies
- Linear-model fit (shared solver with META-224 RFE)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** Greedy forward sequential selection with CV-based stopping
- **Alternative to:** META-224 RFE (backward), META-225 Stability Selection, META-226 mRMR, META-231 Boruta
- **Coexists with:** META-227/228/229 (pre-filter to reduce candidate pool)

## Test Plan
- k most informative features plus noise: verify top-k recovered in order
- Tight tol: verify early stop when no improvement
- Collinear pair (both informative): verify only one selected (second yields no CV gain)
- Determinism: verify same seed → same selection sequence
