# META-231 — Boruta Feature Selection (Random Forest Wrapper)

## Overview
**Category:** Feature selection (wrapper, all-relevant)
**Extension file:** `boruta.cpp`
**Replaces/improves:** `BorutaPy` Python reference in `feature_engineering.py`
**Expected speedup:** ≥6x over Python reference
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

Shadow-feature permutation-importance test with iterative elimination (Kursa & Rudnicki 2010).

```
Input: X ∈ ℝ^{n×d}, y, max_iter, α (two-sided Bonferroni), RF hyperparams
Output: per-feature decision ∈ {Confirmed, Rejected, Tentative}

hits[j] ← 0 for all j in 1..d
state[j] ← Tentative
for iter = 1..max_iter:
    X_shadow ← column-wise shuffle of X                  (break x_j–y link)
    X_ext    ← concat(X, X_shadow)                        (2d columns total)
    fit Random Forest on (X_ext, y); get importance I_j for all 2d columns
    max_shadow ← max_{j=d+1..2d}  I_j                      (best random benchmark)
    for j = 1..d where state[j] = Tentative:
        if I_j > max_shadow:
            hits[j] ← hits[j] + 1                         (register a "hit")
    # Two-sided binomial test (prob=0.5, trials=iter)
    for j where state[j] = Tentative:
        p_upper = 1 − BinCDF(hits[j] − 1; iter, 0.5)
        p_lower = BinCDF(hits[j]; iter, 0.5)
        if p_upper < α / d:  state[j] ← Confirmed        (Bonferroni correction)
        elif p_lower < α / d: state[j] ← Rejected
return state
```

- **Time complexity:** O(max_iter · RF_fit_cost(n, 2d))
- **Space complexity:** O(n · 2d) for extended matrix + O(d) for hit counts
- **Convergence:** Early stop when no Tentative features remain or iter = max_iter

## C++ Interface (pybind11)

```cpp
// Boruta with internal Random Forest; returns per-feature confirm/reject/tentative
enum class BorutaDecision : int { Tentative = 0, Confirmed = 1, Rejected = 2 };

struct BorutaOut {
    std::vector<int> decisions;          // BorutaDecision per feature
    std::vector<int> hit_counts;
    std::vector<float> importance_mean;
};

BorutaOut boruta_select(
    const float* X, int n, int d,
    const float* y,
    int max_iter, float alpha, int rf_num_trees,
    int rf_max_depth, unsigned seed
);
```

## Memory Budget
- Runtime RAM: <80 MB (extended 2d matrix + RF forest state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n * 2 * d)`; RF nodes pooled via arena

## Performance Target
- Python baseline: `BorutaPy` with sklearn RF
- Target: ≥6x faster (shared tree-building kernel, parallel trees)
- Benchmark: n ∈ {5k, 20k} × d ∈ {50, 500} × trees ∈ {100, 500}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across RF trees — each thread owns its bootstrap index and node arena. Shared importance accumulator uses `acq_rel` atomics or per-thread buffers + final reduction.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only — RF tree nodes live in a per-tree arena. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. Tree nodes own no external pointers — offsets into arena only.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on split-candidate buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for Gini/entropy impurity sums. Guard `log(0)` via ε.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use exact binomial CDF for small iter; normal approximation for iter > 30.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. Explicit RNG seed for shuffling + bootstrap — no `rand()`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_231.py` | Decisions match BorutaPy for same seed and RF |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than BorutaPy reference |
| 5 | `pytest test_edges_meta_231.py` | d=1, all-noise, max_iter=1, constant feature pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors — RF arenas freed |
| 7 | `TSAN=1 build + pytest` | Zero races across tree threads |
| 8 | Human reviewer | CPP-RULES.md compliance + Bonferroni correction audit |

## Dependencies
- Internal Random Forest implementation (tree builder, bootstrap sampler, importance calc)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** All-relevant feature identification via shadow-feature hypothesis test
- **Alternative to:** META-224 RFE, META-225 Stability Selection, META-226 mRMR, META-230 Forward Selection
- **Coexists with:** META-227/228/229 as pre-filter; Boruta answers "relevant?" vs mRMR's "non-redundant?"

## Test Plan
- Synthetic with k true features, d−k noise: verify all k Confirmed, all d−k Rejected
- All-noise input: verify 0 Confirmed after max_iter
- Tentative residue: verify tentative fraction → 0 as max_iter → ∞
- Determinism: verify same seed → identical decisions across runs
