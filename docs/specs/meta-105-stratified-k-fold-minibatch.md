# META-105 — Stratified k-Fold Mini-Batching

## Overview
**Category:** Class-balanced sampling (P12 robustness & sampling block)
**Extension file:** `stratified_kfold.cpp`
**Replaces/improves:** Random k-fold splitting that may produce folds with severe class imbalance — stratified k-fold preserves per-class proportions in every fold, ensuring each fold contains ≥ 1 example per relevance stratum (essential when buckets have <K examples)
**Expected speedup:** ≥6x over Python `sklearn.model_selection.StratifiedKFold` per call
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: labels y ∈ {0..C-1} of length n, fold count K
Output: fold assignment f ∈ {0..K-1} of length n with
        class proportions in each fold ≈ class proportions in the overall dataset

Stratified assignment (Kohavi 1995, building on Geisser 1975):
  1. Group indices by class: class_buckets[c] = [i : y_i = c]
  2. For each class c:
       Shuffle class_buckets[c] (deterministic with seed)
       Distribute the |c|-many indices round-robin across folds 0..K-1:
           f[class_buckets[c][j]] = j mod K
       (This guarantees each fold gets ⌊|c|/K⌋ or ⌈|c|/K⌉ examples of class c.)
  3. Each fold contains ≥ 1 example per class iff |c| ≥ K for all c.
       If |c| < K for some c, raise an error or fall back to non-stratified
       for that class (caller chooses).

For mini-batch streaming: cycle through fold 0 as the held-out test fold,
mini-batches drawn uniformly from training folds 1..K-1.
```

- **Time complexity:** O(n) total assignment + O(n log n) for the per-class shuffle
- **Space complexity:** O(n) fold-id array + O(C) class buckets
- **Convergence:** Deterministic given seed; produces unbiased K-fold splits matching the original class distribution

## Academic source
Kohavi, R., "A Study of Cross-Validation and Bootstrap for Accuracy Estimation and Model Selection", *Proceedings of the 14th International Joint Conference on Artificial Intelligence (IJCAI)*, 1995. (Builds on Geisser, S., "The Predictive Sample Reuse Method with Applications", *Journal of the American Statistical Association*, 1975.)

## C++ Interface (pybind11)

```cpp
// Assign each example to one of K folds, stratified by class label.
// Returns vector of length n with values in [0, K).
std::vector<int> stratified_kfold_assign(
    const int* labels, int n,
    int K, int C,
    uint64_t rng_seed,
    bool require_class_in_every_fold = true   // raises if |c| < K for some c
);

// Return the (train, test) index lists for fold k (one of the K splits).
struct KFoldSplit { std::vector<int> train; std::vector<int> test; };

KFoldSplit stratified_kfold_split(
    const int* labels, int n,
    int K, int C, int fold_index,
    uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <8 MB at n=1e6 (fold IDs + class buckets)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: pre-sized vectors; one alloc per call

## Performance Target
- Python baseline: `sklearn.model_selection.StratifiedKFold` (Python loop + boilerplate)
- Target: ≥6x faster on n=1e5
- Benchmark: 3 sizes — n ∈ {1e3, 1e5, 1e7} with K=5

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Class buckets pre-sized via one-pass count.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate K ≥ 2, C ≥ 1, all labels in [0, C), n ≥ K.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Bucket-counting pass vectorisable; shuffle is scalar (Fisher-Yates).

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. (No floating point in this algorithm — labels and indices only.)

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. xoshiro256** PRNG embedded for shuffling.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Empty class (|c| = 0) is allowed when `require_class_in_every_fold = false`. K > n raises.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seed required from caller (no silent `random_device`).

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_105.py` | Per-fold class-count matches sklearn StratifiedKFold (allowing seed/order differences) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_stratified.py` | ≥6x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_105.py` | C=1 (degenerates to plain k-fold), |c|<K (raises or fallback), n=K, K=2, K=n handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Stratification check | Per-fold class proportions within ±1 example of overall proportions |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps; embed xoshiro256** PRNG and Fisher-Yates shuffle

## Pipeline stage non-conflict declaration
- **Owns:** Class-stratified K-fold assignment + per-fold (train, test) split extraction
- **Alternative to:** Random K-fold (no class balance guarantee), META-103 reservoir (uniform, not stratified), META-104 importance weighting (probability-weighted)
- **Coexists with:** META-102 OHEM (selects within a fold), META-103 reservoir, META-104 importance weighting; all P8/P9/P10/P11 metas

## Test Plan
- C = 1: degenerates to balanced split; verify each fold has n/K ± 1 examples
- |c| < K with require_class_in_every_fold=true: verify raises
- |c| ≥ K for all c: verify each fold contains ≥ 1 example per class
- Stratification: verify per-fold class proportions within 1 example of overall proportions
- Same seed twice: identical fold assignments
- Train + test indices for fold k: union = all n, intersection = empty
