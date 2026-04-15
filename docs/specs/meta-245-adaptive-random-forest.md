# META-245 — Adaptive Random Forest (ARF)

## Overview
**Category:** Streaming / online learning
**Extension file:** `adaptive_random_forest.cpp`
**Replaces/improves:** Offline random forest when data arrives as a stream with concept drift
**Expected speedup:** ≥5x over River `AdaptiveRandomForestClassifier` per batch
**RAM:** <256 MB | **Disk:** <1 MB

## Algorithm

```
Input: stream of (x_t, y_t), M trees, drift detector (ADWIN)
Output: ensemble prediction ĥ(x) and per-tree drift state

For each tree m = 1..M:
  Tree: online Hoeffding tree with randomised feature subsampling √d
  Drift state: foreground tree f_m, optional background tree b_m
  Detector: ADWIN(W_m) tracking per-tree error

Per sample (x_t, y_t) (paper, Algorithm 1):
  prediction ĥ(x) = weighted-vote( f_1..f_M ) using past-window accuracy
  for each tree m:
    update f_m with (x_t, y_t) using Poisson(λ=6) online bagging
    err_t ← 1 if f_m misclassified else 0
    add err_t to ADWIN(W_m)
    if ADWIN detects drift:
      spawn b_m in background (train on new stream)
    if background ready and outperforms f_m:
      f_m ← b_m

Prediction (paper, eq. 2):
  class = argmax_y Σ_m w_m · [f_m(x) = y]
  w_m ∝ recent window accuracy
```

- **Time complexity:** O(M · depth) per sample
- **Space complexity:** O(M · |tree|)

## Academic Source
Gomes, H. M., Bifet, A., Read, J., Barddal, J. P., Enembreck, F., Pfharinger, B., Holmes, G., and Abdessalem, T. "Adaptive random forests for evolving data stream classification." Machine Learning 106, no. 9 (2017), pp. 1469–1495. DOI: 10.1007/s10994-017-5642-8

## C++ Interface (pybind11)

```cpp
// Online ARF: train and predict on a data stream
struct ARFModel {
    // opaque owning handle to in-memory trees
    uint64_t handle;
};
ARFModel arf_make(int n_trees, int n_features, int n_classes,
                  float lambda, int adwin_delta_exp, uint64_t seed);
void     arf_partial_fit(ARFModel& m, const float* x, int n_samples,
                         const int* y);
std::vector<int> arf_predict(const ARFModel& m, const float* x, int n_samples);
void     arf_free(ARFModel& m);
```

## Memory Budget
- Runtime RAM: <256 MB for M≤100 trees with 50k internal nodes each
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena per tree; freed via `arf_free`

## Performance Target
- Python baseline: `river.ensemble.AdaptiveRandomForestClassifier`
- Target: ≥5x faster per 10k-sample batch
- Benchmark: 10k, 100k, 1M samples × d=32

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Per-tree training can be parallel with `std::for_each(std::execution::par)` and per-tree RNGs. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths — use arena per tree. No `alloca`/VLA. RAII handles.

**Object lifetime:** Self-assignment safe. Background tree promotes to foreground with atomic swap.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** Split criterion scans can vectorise. `alignas(64)` on per-node sufficient stats.

**Floating point:** Flush-to-zero on init. NaN feature → route to majority child. Double accumulator for entropy.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU. Seeded RNG is deterministic.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_245.py` | Accuracy within 2 pp of River ARF on SEA and RandomRBF streams |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than River reference |
| 5 | `pytest test_edges_meta_245.py` | Single class, abrupt drift, gradual drift all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across tree training threads |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-246 Mondrian forest primitives and/or a Hoeffding-tree core
- Depends on ADWIN drift detector (existing or co-spec META-22x)

## Pipeline Stage Non-Conflict
- **Owns:** drift-aware tree replacement and weighted voting
- **Alternative to:** offline random forest, gradient boosting
- **Coexists with:** META-246 (Mondrian forest — different online tree strategy)

## Test Plan
- SEA with abrupt drift at t=50k: verify accuracy recovers within 5k samples after drift
- No drift: verify accuracy monotonically increases
- Single class: verify predicts that class always
- Background tree never promotes when equal accuracy: verify foreground preserved
