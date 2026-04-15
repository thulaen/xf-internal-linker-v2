# META-248 — Incremental PCA

## Overview
**Category:** Online decomposition
**Extension file:** `incremental_pca.cpp`
**Replaces/improves:** Full-batch PCA on the whole corpus when data does not fit in RAM
**Expected speedup:** ≥6x over `sklearn.decomposition.IncrementalPCA`
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: current top-k decomposition (U, Σ, V), new batch B ∈ ℝ^{m×d}
Output: updated top-k (U', Σ', V')

Maintain running mean μ_n (paper, eq. 5):
  μ_{n+m} = (n · μ_n + m · μ_B) / (n + m)

Centre batch: B ← B − μ_{n+m}  (correcting for shifted mean)

Rank-k SVD update (paper, Algorithm 1):
  Form augmented matrix:
    M = [ U · Σ ; B − μ_shift_correction ]
  Run thin SVD on M:
    M = U_new · Σ_new · V_newᵀ
  Truncate to top-k:
    U' ← first k columns of U_new
    Σ' ← diag of first k
    V' ← first k rows of V_newᵀ

Equivalent Brand-style formulation uses QR of residual — see META-249.
Ross Lim Lin Yang (IJCV 2008) framing targets tracking/visual domains.
```

- **Time complexity:** O((k + m)² · d) per batch (dominated by SVD of (k+m)×d)
- **Space complexity:** O(k · d)

## Academic Source
Ross, D. A., Lim, J., Lin, R.-S., and Yang, M.-H. "Incremental learning for robust visual tracking." International Journal of Computer Vision 77, no. 1–3 (2008), pp. 125–141. DOI: 10.1007/s11263-007-0075-7

## C++ Interface (pybind11)

```cpp
struct IPCAState {
    std::vector<float> components;   // k × d
    std::vector<float> sing_values;  // k
    std::vector<float> mean;         // d
    int k, d;
    int64_t n_seen;
};
IPCAState ipca_init(int k, int d);
void      ipca_partial_fit(IPCAState& s, const float* batch, int m);
std::vector<float> ipca_transform(const IPCAState& s,
                                  const float* X, int n);
```

## Memory Budget
- Runtime RAM: <64 MB (components + one batch for k≤256, d≤2048, m≤1024)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(k*d)`; `alignas(64)` on components

## Performance Target
- Python baseline: `sklearn.decomposition.IncrementalPCA`
- Target: ≥6x faster via LAPACK `gesdd` on augmented matrix
- Benchmark: k=32, d=512, m=512 across 100 batches

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** LAPACK calls may be multi-threaded — pin thread count via env. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on augmented matrix.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for mean update. Σ values clamped ≥ 0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_248.py` | Components match sklearn IncrementalPCA within 1e-3 (up to sign) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than sklearn reference |
| 5 | `pytest test_edges_meta_248.py` | k=1, batch size = 1, singular batch, zero variance features handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-218 (LAPACK bindings) for `gesdd`
- Co-exists with META-249 Online SVD (Brand) which uses a different rank-1 update path

## Pipeline Stage Non-Conflict
- **Owns:** top-k PCA tracking with running mean correction
- **Alternative to:** offline `numpy.linalg.svd` of the whole matrix
- **Coexists with:** META-249 (Brand's method does strict rank-1 updates; this spec does rank-m batch updates)

## Test Plan
- Batched gaussian: verify components match sklearn IncrementalPCA up to sign
- m = 1 updates: verify matches rank-1 streaming PCA
- k = d: verify reconstruction error → 0 as batches grow
- Zero-variance feature: verify singular value is 0 and component is zero
