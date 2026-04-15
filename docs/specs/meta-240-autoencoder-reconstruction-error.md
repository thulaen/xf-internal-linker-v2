# META-240 — Autoencoder Reconstruction Error

## Overview
**Category:** Anomaly detection — reconstruction based
**Extension file:** `autoencoder_recon.cpp`
**Replaces/improves:** Purely geometric anomaly scores (LOF, OC-SVM) when data has non-linear structure
**Expected speedup:** ≥5x over NumPy MLP forward pass for inference
**RAM:** <128 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, encoder/decoder parameters θ
Output: reconstruction error score per sample

Architecture:
  z = encoder(x; θ_e)        z ∈ ℝ^{d_bottleneck}
  x̂ = decoder(z; θ_d)        x̂ ∈ ℝ^d

Training objective (paper, Section 3):
  L(θ) = (1/N) · Σ_i ‖x_i − decoder(encoder(x_i))‖²
  θ ← Adam on L

Anomaly score (paper, eq. 1):
  s(x) = ‖x − decoder(encoder(x))‖²

Flag as anomaly if:
  s(x) > q_{1−α}(s_train)   — empirical quantile threshold

Layer-wise activation: ReLU (or tanh) between dense layers;
final decoder layer has identity/linear activation.
```

- **Time complexity:** O(n · sum_layer (d_in · d_out)) per forward
- **Space complexity:** O(sum_layer (d_in · d_out)) for θ plus O(n · max_layer_width) scratch

## Academic Source
Sakurada, M., and Yairi, T. "Anomaly detection using autoencoders with nonlinear dimensionality reduction." Proceedings of the 2nd Workshop on Machine Learning for Sensory Data Analysis (MLSDA), 2014. DOI: 10.1145/2689746.2689747

## C++ Interface (pybind11)

```cpp
// Fused forward pass: encoder then decoder, returning MSE per sample
std::vector<float> autoencoder_reconstruction_error(
    const float* X, int n, int d,
    const float* encoder_weights, const int* encoder_dims, int n_enc_layers,
    const float* decoder_weights, const int* decoder_dims, int n_dec_layers,
    int activation_kind   // 0=relu, 1=tanh
);
```

## Memory Budget
- Runtime RAM: <128 MB (weight tensors + activation scratch for n≤10k batch)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(batch*max_layer_width)`

## Performance Target
- Python baseline: NumPy dense matmul + np.maximum ReLU
- Target: ≥5x faster via BLAS gemm + fused ReLU
- Benchmark: 1k, 10k, 100k samples × d=128, bottleneck=16

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on weights and activations.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for MSE per sample. ReLU `max(0, x)` keeps values finite.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_240.py` | Error matches Python reference forward within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than NumPy reference |
| 5 | `pytest test_edges_meta_240.py` | Identity AE (zero error), all-zero weights, NaN inputs handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Training lives in PyTorch / Keras (outside this extension). Inference only is in C++.
- Co-exists with META-237, META-238, META-239 anomaly detectors

## Pipeline Stage Non-Conflict
- **Owns:** per-sample reconstruction MSE score
- **Alternative to:** META-237 LOF, META-238 OC-SVM, META-239 Elliptic envelope
- **Coexists with:** META-76 / other embedding pipelines (this extension consumes their outputs)

## Test Plan
- Identity autoencoder (W_d = W_e⁺): verify reconstruction error ≈ 0
- Random data through random AE: verify error distribution matches PyTorch reference
- Input dim mismatch: verify raises ValueError
- NaN in input: verify returns NaN score (not crash)
