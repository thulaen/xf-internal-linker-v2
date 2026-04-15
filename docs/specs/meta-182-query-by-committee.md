# META-182 — Query by Committee

## Overview
**Category:** Active learning query strategy (ensemble disagreement)
**Extension file:** `query_by_committee.cpp`
**Replaces/improves:** Single-model uncertainty in META-181 when calibration is poor
**Expected speedup:** ≥6x over Python committee-vote-entropy loop
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm

```
Input: unlabeled pool U = {x_1..x_N}, committee H = {h_1..h_C} of C classifiers
Output: next query x* with maximum committee disagreement

for each x in U:
    votes[y] = 0 for all labels y
    for i = 1..C:
        y_hat_i = h_i(x)
        votes[y_hat_i] += 1
    p_hat[y] = votes[y] / C
    VoteEntropy(x) = − Σ_y p_hat[y] · log(p_hat[y])

x* = argmax_{x in U} VoteEntropy({h_i(x)}_{i=1..C})
```

- **Paper update rule (Seung/Opper/Sompolinsky):** select `x* = argmax_x VoteEntropy({h_i(x)}_{i=1..C})` where committee of C models disagree
- **Time complexity:** O(|U| · C + |U| · Y) per query (Y = distinct labels voted)
- **Space complexity:** O(|U|) scores + O(C·Y) vote tallies

## Academic Source
Seung, H. S., Opper, M. & Sompolinsky, H. (1992). "Query by Committee". COLT '92, Proceedings of the Fifth Annual Workshop on Computational Learning Theory, pp. 287-294. DOI: 10.1145/130385.130417

## C++ Interface (pybind11)

```cpp
// preds_matrix[i*C + c] = committee member c's predicted label for sample i
std::vector<int> query_by_committee(
    const int* preds_matrix, int n_samples, int n_committee,
    int n_classes,
    int top_k
);
```

## Memory Budget
- Runtime RAM: <24 MB for |U|=1e6 at C=11 (44 MB pred ints + 4 MB scores)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: flat `std::vector<int>` tally per row, reused

## Performance Target
- Python baseline: `scipy.stats.mode` + entropy per row
- Target: ≥6x faster (SIMD histogram via AVX2 gather-scatter)
- Benchmark: 3 sizes — |U|=1e3, 1e5, 1e6 at C=11

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** No mutex (per-row independent). `#pragma omp parallel for` with private tally arrays.

**Memory:** No raw `new`/`delete`. `std::vector<int>` tally `reserve(n_classes)`. Bounds-checked in debug.

**Object lifetime:** No dangling refs to row buffers.

**Type safety:** Explicit `static_cast` narrowing. Label bounds validated (`0 ≤ label < n_classes`).

**SIMD:** AVX2 log reduction; `_mm256_zeroupper()` on exit. `alignas(64)` on scores.

**Floating point:** Flush-to-zero. Clamp `p_hat` to [1e-12, 1] before log.

**Performance:** No `std::function` inside OMP loop. No `dynamic_cast`.

**Error handling:** Validate committee size ≥ 2. Destructors `noexcept`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace helpers.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_182.py` | Matches modAL QBC within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_182.py` | C=1, C=2, all-agree, all-disagree, OOB label |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP parallel loop |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; upstream supplies committee predictions)

## Pipeline Stage Non-Conflict
- **Owns:** Committee-based disagreement scoring for query selection
- **Alternative to:** META-181 (single-model uncertainty), META-183 (EMC), META-184 (density)
- **Coexists with:** META-186 (self-training) — QBC can seed self-training's confident set

## Test Plan
- C=3 full-agree: verify VoteEntropy = 0
- C=3 equal split across 3 classes: verify entropy = log(3)
- C=1 committee: verify raises ValueError (degenerate)
- Label out-of-bounds: verify raises ValueError
- |U|=0 empty pool: verify returns empty vector
