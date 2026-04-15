# META-247 — Mini-batch k-means

## Overview
**Category:** Online clustering / decomposition
**Extension file:** `minibatch_kmeans.cpp`
**Replaces/improves:** Full-batch k-means when data is too large for RAM or arrives as a stream
**Expected speedup:** ≥10x over full-batch Lloyd's at comparable quality
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: centers c_1..c_K, mini-batch size b, max_iters, reassignment ratio
Output: updated centers c_1..c_K

Initialise c_j (k-means++), counters n_j ← 0.

At each step t = 1..max_iters (paper, Algorithm 1):
  sample mini-batch M of b points (with replacement).
  for each x ∈ M:
    j ← argmin_k ‖x − c_k‖²             # nearest centre
    d(x) ← j
  for each x ∈ M:
    n_{d(x)} ← n_{d(x)} + 1
    η ← 1 / n_{d(x)}                     # per-centre learning rate
    c_{d(x)} ← (1 − η) · c_{d(x)} + η · x

Optional (Sculley, Section 3): occasional centre reassignment of underused
centres to points with highest residual.

Convergence: centres change less than tol between two consecutive iterations.
```

- **Time complexity:** O(iters · b · K · d)
- **Space complexity:** O(K · d + b · d)

## Academic Source
Sculley, D. "Web-scale k-means clustering." Proceedings of the 19th International Conference on World Wide Web (WWW 2010), pp. 1177–1178. DOI: 10.1145/1772690.1772862

## C++ Interface (pybind11)

```cpp
// Stateful mini-batch k-means
struct MBKMeansState {
    std::vector<float> centers;    // K*d
    std::vector<int>   counts;     // K
    int K, d;
};
MBKMeansState mbkmeans_init(const float* init_centers, int K, int d);
void mbkmeans_partial_fit(MBKMeansState& s, const float* batch, int b);
std::vector<int> mbkmeans_predict(const MBKMeansState& s,
                                  const float* X, int n);
```

## Memory Budget
- Runtime RAM: <64 MB (centers + batch scratch for K≤4096, b≤10k)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(K*d)`; `alignas(64)` on centres

## Performance Target
- Python baseline: `sklearn.cluster.MiniBatchKMeans`
- Target: ≥10x faster via SIMD pairwise distance on mini-batch
- Benchmark: n=100k, 1M, 10M × K=256 × d=64

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Multi-thread across mini-batch items with per-thread local centre deltas merged at end. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on centres.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for centre update when n_j > 10⁶. Division `1/n_j` safe since n_j starts at 1 on first visit.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_247.py` | Final inertia within 5% of sklearn MiniBatchKMeans on blob data |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥10x faster than sklearn reference |
| 5 | `pytest test_edges_meta_247.py` | K=1, K=n, NaN batch, empty cluster handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across worker threads |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Co-exists with META-45 (full-batch k-means) and META-216 (density-based clustering)

## Pipeline Stage Non-Conflict
- **Owns:** streaming centroid updates with per-centre learning rate
- **Alternative to:** full-batch Lloyd's k-means
- **Coexists with:** META-248 Incremental PCA (often used together for a streaming pipeline)

## Test Plan
- 3 gaussian blobs: verify assignments match true clusters within 95% after 1k mini-batches
- K = 1: verify centre converges to global mean
- NaN point in batch: verify skipped and logged
- Empty cluster mid-training: verify reassignment picks it up (Sculley section 3)
