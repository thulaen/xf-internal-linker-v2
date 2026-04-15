# META-190 — FixMatch

## Overview
**Category:** Semi-supervised learning (weak-strong augmentation consistency)
**Extension file:** `fixmatch.cpp`
**Replaces/improves:** MixMatch (META-189) by replacing sharpening with a hard pseudo-label threshold
**Expected speedup:** ≥5x over Python weak/strong prob + masked CE loop
**RAM:** <48 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled batch (x_l, y_l), unlabelled batch x_u,
       weak aug α(·), strong aug A(·),
       threshold τ, unsupervised weight λ_u
Output: supervised loss L_s, consistency loss L_u per step

Labelled term:
    L_s = CE(p_model(y | α(x_l)), y_l)

Pseudo-labels from weak aug:
    q̂ = argmax_y p_model(y | α(x_u))
    mask = 1 if max p_model(y | α(x_u)) > τ else 0

Consistency term on strong aug:
    L_u = mask · CE(q̂, p_model(y | A(x_u)))

L = L_s + λ_u · L_u
```

- **Paper update rule (Sohn et al.):** weak augmentation gives pseudo-label `q̂ = argmax p_model(y|α(x))` if `max q̂ > τ`; consistency loss `CE(q̂, p_model(y|A(x)))` on strong aug A
- **Time complexity:** O(B · C) per batch step
- **Space complexity:** O(B) mask + O(B) pseudo-labels

## Academic Source
Sohn, K., Berthelot, D., Carlini, N., Zhang, Z., Li, C.-L., Cubuk, E. D., Kurakin, A., Zhang, H. & Raffel, C. (2020). "FixMatch: Simplifying Semi-Supervised Learning with Consistency and Confidence". NeurIPS 2020. arXiv:2001.07685

## C++ Interface (pybind11)

```cpp
// Compute mask, pseudo-label, and per-sample unsupervised CE. Reduction done in caller.
struct FixmatchStep {
    std::vector<int> pseudo_labels;   // [B_u]
    std::vector<uint8_t> mask;        // [B_u]  0/1
    std::vector<float> per_sample_u;  // [B_u]  CE(q̂, p_strong) before masking
};
FixmatchStep fixmatch_step(
    const float* probs_weak,    // [B_u, n_classes]
    const float* probs_strong,  // [B_u, n_classes]
    int B_u, int n_classes,
    float tau
);
```

## Memory Budget
- Runtime RAM: <48 MB for B_u=1e4, C=10 (~800 KB probs + small outputs); scales with batch
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: output vectors `reserve(B_u)`; no per-row heap

## Performance Target
- Python baseline: `argmax + (max>τ) + masked cross-entropy` per batch
- Target: ≥5x faster via fused single-pass
- Benchmark: 3 sizes — B_u=256/C=10, B_u=2048/C=10, B_u=10000/C=1000

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel OpenMP; per-sample independence makes this trivial.

**Memory:** No raw `new`/`delete`. `reserve()` before fills. Bounds-checked in debug.

**Object lifetime:** Read-only probs pointers; POD output struct.

**Type safety:** Explicit `static_cast` narrowing. `τ ∈ [0,1]` validated.

**SIMD:** AVX2 fused max + argmax on weak, `_mm256_log_ps` approx on strong. `_mm256_zeroupper()`. `alignas(64)` rows.

**Floating point:** Clamp strong probs to [1e-12, 1] before log. NaN row zeroed with mask=0.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Single sweep over both matrices row-by-row.

**Error handling:** Destructors `noexcept`. Validate shape equality weak/strong. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_190.py` | Matches PyTorch FixMatch reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than PyTorch reference |
| 5 | `pytest test_edges_meta_190.py` | τ=0 (all kept), τ=1 (none kept), NaN, shape mismatch |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Upstream DL framework provides weak and strong augmented posteriors

## Pipeline Stage Non-Conflict
- **Owns:** Consistency-loss preparation (mask + pseudo-label + per-sample CE)
- **Alternative to:** META-186 (self-training), META-189 (MixMatch)
- **Coexists with:** META-183 (EMC) — FixMatch mask can gate which samples contribute to EMC estimate

## Test Plan
- τ=0: verify mask = all ones
- τ=1: verify mask = all zeros (strict >)
- Weak = Strong exactly: verify per_sample_u = 0 for masked rows
- NaN row in weak: verify mask=0 for that row, no crash
- B_u=0: verify empty outputs
