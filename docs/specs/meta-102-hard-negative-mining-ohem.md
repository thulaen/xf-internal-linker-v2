# META-102 — Hard Negative Mining (OHEM)

## Overview
**Category:** Sampling for training (P12 robustness & sampling block)
**Extension file:** `ohem.cpp`
**Replaces/improves:** Uniform-loss mini-batches — OHEM keeps only the highest-loss examples for the gradient step, focusing capacity on hard cases (e.g. confusable cross-section internal links)
**Expected speedup:** ≥8x over Python `np.argsort` + slice loop
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: per-example losses ℓ_i for i = 1..B (mini-batch size), target keep-count k
Output: index set I* ⊂ {1..B} with |I*| = k of top-k loss examples

Compute losses ℓ_i for all B examples in batch (forward pass kept).
Select top-k by loss:
  partial_sort or nth_element on ℓ to find top-k indices
Mask: only top-k examples contribute to backward gradient
  ∇_w L_OHEM = (1/k) · Σ_{i ∈ I*} ∇_w ℓ_i

Variant — class-aware OHEM:
  Maintain per-class quotas (paper's positive : negative ratio, e.g. 1:3)
  Within each class, select top-k_class
```

- **Time complexity:** O(B) for `nth_element` selection (vs O(B log B) for full sort)
- **Space complexity:** O(B) loss + index arrays
- **Convergence:** Standard SGD on the sub-batch; effective when full batch loss is dominated by easy examples

## Academic source
Shrivastava, A., Gupta, A. and Girshick, R., "Training Region-based Object Detectors with Online Hard Example Mining", *IEEE Conference on Computer Vision and Pattern Recognition (CVPR)*, 2016. DOI 10.1109/CVPR.2016.89.

## C++ Interface (pybind11)

```cpp
// Select top-k indices by loss using nth_element (O(B) average)
std::vector<int> ohem_select(
    const float* losses, int B, int k
);

// Class-aware variant: per-class quotas summing to k
std::vector<int> ohem_select_class_aware(
    const float* losses, const int* class_id, int B,
    const int* per_class_k, int n_classes
);

// Convenience: build a 0/1 mask of length B
void ohem_mask(
    const float* losses, int B, int k,
    int* mask_out
);
```

## Memory Budget
- Runtime RAM: <8 MB at B=1e6 (loss + index buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized index buffer, no per-call alloc beyond return vector

## Performance Target
- Python baseline: `np.argsort(losses)[-k:]` (O(B log B))
- Target: ≥8x faster on B=1e5 (`std::nth_element` is O(B), avoids full sort and Python overhead)
- Benchmark: 3 sizes — B ∈ {1e3, 1e5, 1e6}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Index buffer reused via thread-local instance.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate 1 ≤ k ≤ B; class IDs in [0, n_classes).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Selection itself is data-dependent (cannot vectorise nth_element); the mask-building pass is vectorised.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. NaN losses sort to last (well-defined comparator); document that NaN examples are excluded from selection.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use `std::nth_element` (partial sort), not `std::sort`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. k > B raises. k = 0 returns empty.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_102.py` | Selected indices = NumPy argpartition top-k (set equality, ties allowed) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_ohem.py` | ≥8x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_102.py` | k=1, k=B, ties, NaN losses, B=1, class-aware quotas summing to >B handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Selection correctness | All selected losses ≥ all unselected losses |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Top-k loss selection (uniform and class-aware)
- **Alternative to:** Uniform mini-batch sampling, META-100/101 DRO (different mechanism — explicit subset vs reweighted)
- **Coexists with:** META-103 reservoir, META-104 importance weighting, META-105 stratified k-fold; all P8 regularisers, P9 calibrators, P10 schedulers, P11 averagers

## Test Plan
- All-equal losses: any k indices acceptable; verify exactly k returned
- B = 1: returns [0]
- k = B: returns full batch
- NaN loss: not selected (well-defined comparator); verify deterministic exclusion
- Class-aware: per_class_k sums equal k; verify quotas honoured exactly
