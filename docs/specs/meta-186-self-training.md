# META-186 — Self-Training

## Overview
**Category:** Semi-supervised learning (bootstrap from pseudo-labels)
**Extension file:** `self_training.cpp`
**Replaces/improves:** Supervised-only training when labelled data is scarce
**Expected speedup:** ≥5x over Python threshold-filter + argmax pipeline per round
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled set L, unlabelled pool U, classifier h, confidence threshold τ
Output: augmented labelled set L' for next training round

Train h on L
Predict posteriors P(y|x) for all x in U
for each x in U:
    ŷ = argmax_y P(y|x)
    if max_y P(y|x) > τ:
        add (x, ŷ) to L'
retrain h on L ∪ L'
```

- **Paper update rule (Scudder):** pseudo-label `ŷ = argmax_y P(y|x)` if `max_y P(y|x) > τ`; add (x, ŷ) to training set; retrain
- **Time complexity:** O(|U| · C) per selection pass
- **Space complexity:** O(|U|) confidence + pseudo-label pair

## Academic Source
Scudder, H. J. (1965). "Probability of Error of Some Adaptive Pattern-Recognition Machines". IEEE Transactions on Information Theory, Vol. 11, No. 3, pp. 363-371. DOI: 10.1109/TIT.1965.1053799

## C++ Interface (pybind11)

```cpp
// Return pairs (index, pseudo_label) for all unlabelled samples above threshold τ
struct Pseudolabel { int index; int label; float confidence; };
std::vector<Pseudolabel> self_training_select(
    const float* probs_matrix, int n_samples, int n_classes,
    float tau
);
```

## Memory Budget
- Runtime RAM: <24 MB for |U|=1e6 at C=10 (40 MB probs + ~12 MB pseudo-label list)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector<Pseudolabel>` with `reserve(n_samples)` upper bound

## Performance Target
- Python baseline: `probs.max(axis=1) > tau` + `probs.argmax(axis=1)`
- Target: ≥5x faster (fused max + argmax in a single AVX2 pass)
- Benchmark: 3 sizes — |U|=1e3, 1e5, 1e6 at C=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel via OpenMP; per-thread output vector merged after.

**Memory:** No raw `new`/`delete`. `reserve()` on output. Bounds-checked in debug.

**Object lifetime:** Read-only probs pointer; Pseudolabel struct is POD.

**Type safety:** Explicit `static_cast` narrowing. `0 ≤ τ ≤ 1` validated.

**SIMD:** AVX2 fused max + argmax (index broadcast on update). `_mm256_zeroupper()` on exit. `alignas(64)` rows.

**Floating point:** Flush-to-zero. NaN probs skipped with explicit check (`_mm256_cmp_ps` unordered).

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Per-thread local vectors, concatenate at end.

**Error handling:** Destructors `noexcept`. Validate probs rows sum ≈ 1. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_186.py` | Matches numpy reference exactly |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than numpy max+argmax |
| 5 | `pytest test_edges_meta_186.py` | τ=0 (all pass), τ=1 (none pass), NaN, uniform |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP merge |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None at selection step (retraining lives in the Python orchestrator)

## Pipeline Stage Non-Conflict
- **Owns:** Threshold-based pseudo-label selection from a single classifier
- **Alternative to:** META-187 (co-training, uses two views), META-190 (FixMatch, augmentation-consistent)
- **Coexists with:** META-181 (uncertainty) — self-training is the complement; active learning asks, self-training answers

## Test Plan
- τ=0: verify every sample selected
- τ=1: verify no sample selected (strict >)
- Uniform prob (1/C): verify no sample selected when C ≥ 2, τ > 1/C
- NaN row: verify row skipped, no crash
- |U|=0: verify returns empty vector
