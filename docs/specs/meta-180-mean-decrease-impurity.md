# META-180 — Mean Decrease Impurity

## Overview
**Category:** Tree-intrinsic feature importance
**Extension file:** `mdi_importance.cpp`
**Replaces/improves:** `sklearn.ensemble.*.feature_importances_` Python aggregation loop
**Expected speedup:** ≥6x for large forests (500 trees × 100k samples)
**RAM:** <100 MB | **Disk:** <1 MB

## Algorithm

```
Input: trained ensemble of decision trees T = {t_1, ..., t_L}
Output: importance vector imp ∈ ℝ^d

for each tree t in T:
    for each internal node v splitting on feature j:
        Δ_v = (N_v / N) · ( impurity_v − (N_left/N_v)·impurity_left − (N_right/N_v)·impurity_right )
        MDI_j += Δ_v
MDI_j /= L     # mean over the forest
optionally normalise so Σ_j MDI_j = 1
```

- **Time complexity:** O(L · M) where M = total internal nodes
- **Space complexity:** O(d) for the accumulator
- **Convergence:** Deterministic closed-form given the fitted trees

## Academic Source
Breiman L., "Random forests," *Machine Learning* 45(1):5–32, 2001. DOI: 10.1023/A:1010933404324

## C++ Interface (pybind11)

```cpp
// Aggregate MDI across a packed forest representation
void mdi_importance(
    const int* feature_per_node,        // shape: total_nodes
    const float* impurity_per_node,     // shape: total_nodes
    const int* n_samples_per_node,      // shape: total_nodes
    const int* left_child, const int* right_child,
    int total_nodes, int n_trees, int n_features,
    int total_N,
    bool normalise,
    float* out_importance
);
```

## Memory Budget
- Runtime RAM: <100 MB for a forest with 1M total nodes
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` sized `n_features`, `reserve()` once

## Performance Target
- Python baseline: sklearn `feature_importances_` loop
- Target: ≥6x faster for 500 trees × 100k samples
- Benchmark: trees ∈ {100, 500, 2000}, n_features ∈ {10, 100, 1000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Per-tree accumulation parallelised with OpenMP, using per-thread local arrays then reduced at the end (no atomic writes in hot loop).

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. Inputs are read-only views of sklearn's packed tree arrays — document lifetime in the header.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch. `feature_per_node[v] == -1` marks leaves; skip without a branch on the hot path where possible.

**SIMD:** `alignas(64)` on accumulator. Final reduction uses AVX2 adds across thread buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on impurities. Double accumulator per feature (forests can have millions of nodes).

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Validate `feature_per_node[v] ∈ [−1, n_features)` once up-front.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_180.py` | Matches sklearn `feature_importances_` within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than sklearn aggregation |
| 5 | `pytest test_edges_meta_180.py` | Empty forest, single-node tree, constant target handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in per-tree parallel reduction |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (consumes the packed tree arrays already produced by sklearn / our own forest trainer)

## Pipeline Stage Non-Conflict
- **Owns:** Tree-intrinsic MDI importance aggregation across the forest.
- **Alternative to:** META-176 (permutation), META-177 (SHAP) — different lenses. MDI is fast but biased toward high-cardinality features; this bias is documented at call-site.
- **Coexists with:** Permutation importance in the diagnostics dashboard for cross-check.
- No conflict with ranking: attribution runs offline on trained models only.

## Test Plan
- Random forest on synthetic data with known informative features: verify those feature MDIs dominate
- Constant target: verify MDIs ≈ 0
- Single-node (stump) tree: verify only the root feature contributes
- Normalise flag: verify Σ imp = 1 when enabled
- Invalid feature index in tree array: verify raises ValueError
