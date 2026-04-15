# META-246 — Mondrian Forest

## Overview
**Category:** Streaming / online learning (tree based)
**Extension file:** `mondrian_forest.cpp`
**Replaces/improves:** Offline random forest when data is added incrementally
**Expected speedup:** ≥6x over `scikit-garden` `MondrianForestClassifier` for partial_fit
**RAM:** <256 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples (x_1..x_n), M trees
Output: Mondrian forest ensemble

Mondrian process on [a, b] hyperrectangle (paper, Algorithm 1):
  Each node has lifetime τ (parent τ_parent).
  Hold rate λ = Σ_d (b_d − a_d).
  Split time E ~ Exp(λ).
  If τ_parent + E ≥ budget T: node is a leaf.
  Else: sample split dim d with prob ∝ (b_d − a_d),
         sample split location u ~ Uniform(a_d, b_d),
         create two children with updated box and τ = τ_parent + E.

Online extension (paper, Algorithm 3):
  For new point x:
    walk root → leaf, extending boxes as needed.
    when x falls outside current box, insert a new split (pseudo-leaf)
    between the violating node and its parent using the Mondrian process.
  Maintain posterior class counts per leaf.

Prediction (paper, eq. 12):
  P(y | x) = hierarchical smoothing along the root-to-leaf path, each
  level weighted by (1 − exp(−Δτ · d_box(x))).
```

- **Time complexity:** O(depth) per sample for fit and predict
- **Space complexity:** O(|tree|) per tree

## Academic Source
Lakshminarayanan, B., Roy, D. M., and Teh, Y. W. "Mondrian forests: Efficient online random forests." Advances in Neural Information Processing Systems 27 (NIPS 2014). https://proceedings.neurips.cc/paper/2014/hash/d1dc3a8270a6f9394f88847d7f0050cf-Abstract.html

## C++ Interface (pybind11)

```cpp
// Online Mondrian forest
struct MondrianForest {
    uint64_t handle;
};
MondrianForest mondrian_make(int n_trees, int n_features, int n_classes,
                             float budget_T, uint64_t seed);
void mondrian_partial_fit(MondrianForest& m, const float* x, int n_samples,
                          const int* y);
std::vector<float> mondrian_predict_proba(const MondrianForest& m,
                                          const float* x, int n_samples);
void mondrian_free(MondrianForest& m);
```

## Memory Budget
- Runtime RAM: <256 MB for 100 trees × n≤1M total nodes; add-only via arena
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: per-tree arena growing in 64 KB pages

## Performance Target
- Python baseline: `scikit-garden` MondrianForest
- Target: ≥6x faster per 10k-sample partial_fit
- Benchmark: 10k, 100k, 1M samples × d=32

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Per-tree training parallel with per-thread RNGs. No `volatile`. No detached threads.

**Memory:** Arena allocator per tree, growth monitored. No raw `new`/`delete` in hot paths.

**Object lifetime:** Self-assignment safe. Pointer-free node indices within arena.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** Boundary checks on hyperrectangle can vectorise over d.

**Floating point:** Flush-to-zero on init. NaN feature → skip sample with log warning. Exponential sampling clamped `max(λ, 1e-9)`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU. Seeded RNG is deterministic.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_246.py` | Accuracy within 2 pp of scikit-garden on MNIST stream |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than scikit-garden reference |
| 5 | `pytest test_edges_meta_246.py` | Single sample, high-d sparse, concept drift-under-budget all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across tree threads |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Standalone tree primitive
- Used by META-245 (ARF) as an option for per-tree online learner

## Pipeline Stage Non-Conflict
- **Owns:** Mondrian-process split generation and online box extension
- **Alternative to:** Hoeffding trees (META-245 default)
- **Coexists with:** META-245 Adaptive Random Forest (uses this as the tree primitive)

## Test Plan
- Static 2D dataset: verify predictions match offline random forest within 2 pp
- Extending budget T: verify more splits appear
- All features equal in a leaf: verify prediction = smoothed prior
- Extremely tall tree with budget → ∞: verify no stack overflow (iterative traversal)
