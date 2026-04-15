# META-187 — Co-Training

## Overview
**Category:** Semi-supervised learning (two-view mutual teaching)
**Extension file:** `co_training.cpp`
**Replaces/improves:** Single-view self-training (META-186) when features decompose into two conditionally-independent views
**Expected speedup:** ≥5x over Python two-model threshold-intersect loop
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled L (with two views X = (X₁, X₂)), unlabelled pool U
       classifiers h₁ (view 1) and h₂ (view 2), confidence thresholds τ₁, τ₂
       per-round caps k₁, k₂ per class
Output: augmented labelled sets L₁', L₂' for next round

Train h₁ on L using X₁ only
Train h₂ on L using X₂ only
for each x in U:
    if max_y P₁(y|x) > τ₁:
        add (x, argmax P₁) to L₂'    // h₁ teaches h₂
    if max_y P₂(y|x) > τ₂:
        add (x, argmax P₂) to L₁'    // h₂ teaches h₁
Retrain h₁ on L ∪ L₁'; retrain h₂ on L ∪ L₂'
```

- **Paper update rule (Blum & Mitchell):** two views X = (X₁, X₂); classifier h₁ learns on view 1, h₂ on view 2; each teaches the other confident pseudo-labels
- **Time complexity:** O(|U| · C) per round for selection
- **Space complexity:** O(|U|) per view for confidences

## Academic Source
Blum, A. & Mitchell, T. (1998). "Combining Labeled and Unlabeled Data with Co-Training". COLT '98, Proceedings of the 11th Annual Conference on Computational Learning Theory, pp. 92-100. DOI: 10.1145/279943.279962

## C++ Interface (pybind11)

```cpp
// Two independent posterior matrices, one per view. Returns (L1_add, L2_add).
struct CoTrainBatch {
    std::vector<int> L1_indices;  std::vector<int> L1_labels;
    std::vector<int> L2_indices;  std::vector<int> L2_labels;
};
CoTrainBatch co_training_select(
    const float* probs_view1, const float* probs_view2,
    int n_samples, int n_classes,
    float tau1, float tau2, int cap_per_class
);
```

## Memory Budget
- Runtime RAM: <32 MB for |U|=5e5 at C=10 (40 MB probs×2 + ~10 MB output lists)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `reserve(n_samples)` on each output vector

## Performance Target
- Python baseline: two separate max/argmax passes + per-class caps in Python
- Target: ≥5x faster via fused single-pass over both views
- Benchmark: 3 sizes — |U|=1e3, 1e5, 5e5 at C=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel OpenMP. Per-thread output buffers merged under lock-free append.

**Memory:** No raw `new`/`delete`. `reserve()` on outputs. Bounds-checked in debug.

**Object lifetime:** Read-only probs pointers; POD output structs.

**Type safety:** Explicit `static_cast` narrowing. Both thresholds ∈ [0,1] validated.

**SIMD:** AVX2 fused max/argmax; `_mm256_zeroupper()` on exit. `alignas(64)` rows.

**Floating point:** Flush-to-zero. NaN row skipped via unordered compare.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Per-class min-heap when `cap_per_class < |U|`.

**Error handling:** Destructors `noexcept`. Validate shape equality view1/view2. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_187.py` | Matches Python two-view reference exactly |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_187.py` | View shape mismatch, τ=0/1, cap=0, cap=|U| |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP append |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Two independently-trained models provide posterior inputs

## Pipeline Stage Non-Conflict
- **Owns:** Mutual pseudo-label exchange between two views
- **Alternative to:** META-186 (single-view self-training), META-188 (graph label propagation)
- **Coexists with:** META-182 (QBC) — the two committee views can seed the two co-training classifiers

## Test Plan
- Views identical: verify L1_add == L2_add
- τ₁=τ₂=1: verify both sets empty
- cap_per_class=1: verify each class gets at most one sample per view
- Shape mismatch view1/view2: verify raises ValueError
- |U|=0: verify empty batch
