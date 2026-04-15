# META-189 — MixMatch

## Overview
**Category:** Semi-supervised learning (augmentation + label guessing + Mixup)
**Extension file:** `mixmatch.cpp`
**Replaces/improves:** Pure threshold pseudo-labelling (META-186) by leveraging augmentation-consistent label guesses
**Expected speedup:** ≥4x over Python numpy sharpen + Mixup broadcasting
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: labelled batch (x_l, y_l), unlabelled batch x_u,
       K augmentations, sharpen temperature T, Mixup α, unsupervised weight λ_u
Output: supervised loss L_x, unsupervised loss L_u for a single training step

for each x in x_u:
    for k = 1..K:  x̂_k = Augment_k(x)
    q_avg = (1/K) · Σ_k p_model(y | x̂_k)
    q̄ = sharpen(q_avg, T)                       // q̄_i ∝ q_avg_i^{1/T}
    (x, q̄) added to guess batch U'

// Mixup labelled and guessed together
W = concat(labelled, U'); shuffled = shuffle(W)
λ ∼ Beta(α, α); λ' = max(λ, 1 − λ)
mixed = λ'·W + (1−λ')·shuffled
L_x = CE on labelled part of mixed
L_u = MSE on unlabelled part of mixed
L   = L_x + λ_u · L_u
```

- **Paper update rule (Berthelot et al.):** augment K times, guess label `q̄ = sharpen((1/K)·Σ p_model(y|x̂_k), T)`, Mixup guesses + labeled; loss = CE(labeled) + λ_u·MSE(unlabeled)
- **Time complexity:** O(B · K · C) guessing + O(B · C) Mixup and loss
- **Space complexity:** O(B · C) mixed batch

## Academic Source
Berthelot, D., Carlini, N., Goodfellow, I., Papernot, N., Oliver, A. & Raffel, C. (2019). "MixMatch: A Holistic Approach to Semi-Supervised Learning". NeurIPS 2019. arXiv:1905.02249

## C++ Interface (pybind11)

```cpp
// Compute label guess + Mixup interpolation. Loss itself runs in the DL framework.
struct MixmatchBatch {
    std::vector<float> mixed_inputs;    // [B, feature_dim]
    std::vector<float> mixed_targets;   // [B, n_classes]
    int supervised_rows;                // first N rows are labelled
};
MixmatchBatch mixmatch_prepare(
    const float* probs_kaug,            // [B_u, K, n_classes] posteriors over K augs
    const float* labels_oh,             // [B_l, n_classes] one-hot
    const float* feats_labelled,        // [B_l, D]
    const float* feats_unlabelled,      // [B_u, D]
    int B_l, int B_u, int K, int C, int D,
    float T, float alpha_beta,
    uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <64 MB for B_l=B_u=256, K=2, D=512, C=10 (1 MB mixed + scratch)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: two `std::vector<float>` mixed buffers `reserve((B_l+B_u)·D)`

## Performance Target
- Python baseline: numpy `mean axis=1 → sharpen → concatenate → shuffle → lerp`
- Target: ≥4x faster (fused sharpen + SIMD lerp)
- Benchmark: 3 sizes — B=64/D=128, B=256/D=512, B=1024/D=768 with K=2, C=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel OpenMP on both sharpen and Mixup.

**Memory:** No raw `new`/`delete`. `reserve()` before fills. Bounds-checked in debug.

**Object lifetime:** Read-only inputs; output struct owns its vectors.

**Type safety:** Explicit `static_cast` narrowing. Validate `T > 0`, `α > 0`.

**SIMD:** AVX2 FMA for lerp (`a·x + (1−a)·y` fused). `_mm256_zeroupper()` on exit. `alignas(64)` on hot rows.

**Floating point:** Flush-to-zero. Clamp sharpened probs to [1e-12, 1]; renormalise to sum=1 per row.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Deterministic RNG (`std::mt19937_64`) seeded per call.

**Error handling:** Destructors `noexcept`. Validate `B_l == B_u` preferred. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`. RNG state not leaked.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_189.py` | Matches PyTorch MixMatch reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_189.py` | K=1, T→0 (one-hot), T=1 (no sharpen), α tiny/huge |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Upstream DL framework provides K augmented posteriors

## Pipeline Stage Non-Conflict
- **Owns:** Label-guess sharpening + Mixup interpolation (data-prep stage)
- **Alternative to:** META-186 (self-training), META-190 (FixMatch)
- **Coexists with:** META-04 (coord ascent) — MixMatch-trained scorer becomes input to weight tuning

## Test Plan
- K=1: verify q_avg = posterior (no averaging)
- T → 0⁺: verify q̄ becomes one-hot on argmax
- T = 1: verify q̄ = q_avg (no sharpening)
- λ'=1 (Beta α large): verify mixed = W, no contribution from shuffled
- RNG determinism: verify identical output for identical seed
