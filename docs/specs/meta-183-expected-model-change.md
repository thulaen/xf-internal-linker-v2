# META-183 — Expected Model Change (EMC)

## Overview
**Category:** Active learning query strategy (gradient-magnitude)
**Extension file:** `expected_model_change.cpp`
**Replaces/improves:** Entropy/QBC when model has large gradient signal per sample
**Expected speedup:** ≥5x over Python PyTorch autograd loop
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: unlabeled pool U, model parameters θ, loss ∇L, posterior P(y|x)
Output: next query x* with maximum expected gradient magnitude

for each x in U:
    p_y = P(y|x)                          // C-class posterior
    grad_norms = [0] * C
    for each label y in 1..C:
        g_y = ∇_θ L(θ; x, y)              // gradient if x were labelled y
        grad_norms[y] = ‖g_y‖_2
    EMC(x) = Σ_y p_y · grad_norms[y]      // expectation under model's own posterior

x* = argmax_{x in U} EMC(x)
```

- **Paper update rule (Settles & Craven):** `EMC(x) = E_{y~P(y|x)}[‖∇_θ L(θ; x,y)‖]` — gradient magnitude under predicted label
- **Time complexity:** O(|U| · C · |θ|) — dominant term is gradient norm
- **Space complexity:** O(|U|) scores + O(|θ|) reusable gradient buffer

## Academic Source
Settles, B. & Craven, M. (2008). "An Analysis of Active Learning Strategies for Sequence Labeling Tasks". EMNLP 2008, pp. 1070-1079. DOI: 10.3115/1613715.1613855

## C++ Interface (pybind11)

```cpp
// Caller precomputes per-(sample, label) gradient L2 norms; this fuses the expectation
std::vector<int> expected_model_change(
    const float* probs_matrix,    // [n_samples, n_classes]
    const float* grad_norm_matrix, // [n_samples, n_classes]
    int n_samples, int n_classes,
    int top_k
);
```

## Memory Budget
- Runtime RAM: <32 MB for |U|=1e6 at C=10 (80 MB inputs, streamed in tiles)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector<float>` scores `reserve(n_samples)`, no per-row heap

## Performance Target
- Python baseline: `numpy.einsum('ij,ij->i', probs, grad_norms)`
- Target: ≥5x faster with AVX2 FMA reduction
- Benchmark: 3 sizes — |U|=1e3, 1e5, 1e6 at C=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel via OpenMP; no shared mutable state.

**Memory:** No raw `new`/`delete`. `std::vector` with `reserve()`. Bounds-checked in debug.

**Object lifetime:** Read-only input pointers; no dangling refs.

**Type safety:** Explicit `static_cast` narrowing. No signed/unsigned mismatch.

**SIMD:** AVX2 FMA `_mm256_fmadd_ps` for inner product. `_mm256_zeroupper()` on exit. `alignas(64)` on hot rows.

**Floating point:** Flush-to-zero. Double accumulator when C ≥ 100. NaN/Inf entry checks on both matrices.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Tiled row traversal for cache.

**Error handling:** Destructors `noexcept`. Validate non-negative grad norms. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_183.py` | Matches numpy einsum within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than numpy einsum |
| 5 | `pytest test_edges_meta_183.py` | Zero grads, NaN, negative prob, |U|=0 |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP parallel loop |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller provides gradient L2 norms (PyTorch/TF side). Spec covers the reduction only.

## Pipeline Stage Non-Conflict
- **Owns:** Expected-gradient-norm scoring per unlabelled sample
- **Alternative to:** META-181 (uncertainty), META-182 (QBC), META-184 (density)
- **Coexists with:** META-04 (coord ascent) — EMC chooses training rows that coord-ascent then weights

## Test Plan
- All zero grads: verify EMC = 0 for every sample
- Uniform prob + equal grads: verify EMC = constant grad norm
- Single label (C=1): verify EMC reduces to grad_norm[0]
- NaN/Inf in grad or prob: verify raises ValueError
- |U|=0: verify returns empty vector
