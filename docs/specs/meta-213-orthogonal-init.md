# META-213 — Orthogonal Initialisation

## Overview
**Category:** Neural-network weight initialisation (depth-stable)
**Extension file:** `init_orthogonal.cpp`
**Replaces/improves:** Python `torch.nn.init.orthogonal_` wrapper for deep ranker stacks and any recurrent-style re-ranking module
**Expected speedup:** ≥3x (Householder-based path avoids full numpy QR)
**RAM:** <50 MB for 4096 × 4096 | **Disk:** <1 MB

## Algorithm

```
Input:  layer shape (n_in, n_out), gain
Output: orthogonal W ∈ ℝ^{n_in × n_out}
Paper construction (Saxe, McClelland, Ganguli, ICLR 2014, §3):

  1. Sample A ∈ ℝ^{max × max}  with  A_ij ~ N(0, 1)   where max = max(n_in, n_out)
  2. QR decomposition: A = Q · R  (Householder; Q is orthogonal)
  3. Fix sign ambiguity: Q ← Q · diag(sign(diag(R)))    (ensures uniform distribution on O(n))
  4. Slice to (n_in, n_out): W = Q[:n_in, :n_out]
  5. Scale: W ← gain · W

Dynamical-isometry property: all singular values of W are exactly 1 (before gain),
so signal propagation through deep stacks is norm-preserving.
```

- **Time complexity:** O(max(n_in, n_out)³) from QR; dominated by Householder reflector application
- **Space complexity:** O(max(n_in, n_out)²)
- **Convergence:** N/A (closed-form)

## Academic Source
Saxe, A. M., McClelland, J. L. & Ganguli, S. "Exact solutions to the nonlinear dynamics of learning in deep linear neural networks." *International Conference on Learning Representations (ICLR 2014)*, arXiv:1312.6120. URL: https://arxiv.org/abs/1312.6120. (ICLR 2014 workshop track; no DOI.)

## C++ Interface (pybind11)

```cpp
// Orthogonal weight init via Householder QR; caller-owned W is filled in place
void orthogonal_init(
    py::array_t<float, py::array::c_style | py::array::forcecast> W,
    int n_in, int n_out,
    float gain = 1.0f,
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <50 MB at max=4096 (A and Q workspace)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: one `std::vector<float>` for Householder workspace, `reserve(max*max)` up-front

## Performance Target
- Baseline: `torch.nn.init.orthogonal_` via CPU numpy path
- Target: ≥3x faster at 4096×4096
- Benchmark: 3 sizes — (64 × 64), (512 × 512), (4096 × 4096)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** Sequential Householder reflector application (chase down diagonal). Optional parallel reflector-apply across columns once the reflector is fixed. No `volatile`.

**Memory:** No raw `new`/`delete`. Arena workspace for A and reflector vectors. Bounds-checked in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for stride arithmetic.

**SIMD:** AVX2 FMA on reflector application H = I − 2·v·vᵀ. `_mm256_zeroupper()` before return. `alignas(64)` on workspace.

**Floating point:** Double accumulator for reflector dot products at max ≥ 1024. NaN/Inf check on final Q. Sign-fix step uses `copysignf`.

**Performance:** No `std::endl`. No `std::function`. `return;` (void).

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on zero dims or shape mismatch.

**Build:** No cyclic includes. Anonymous namespace for QR helpers.

**Security:** No `system()`. No implicit entropy source.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_213.py` | WᵀW ≈ I (or W Wᵀ for wide) within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_213.py` | Square, tall, wide, n_in=1, zero-dim reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- May share Householder utilities with META-206 (SVD); factor into common header if implemented close in time.

## Pipeline Stage Non-Conflict
- **Stage owned:** Layer-weight initialisation for deep / recurrent ranker stacks
- **Owns:** Orthogonal QR-based fill with sign fix
- **Alternative to:** META-211 (Xavier), META-212 (He)
- **Coexists with:** META-214/215/216/217/218 (normalisation layers after init compose freely)

## Test Plan
- 1024×1024 fill: verify WᵀW = I to 1e-5
- Tall matrix 4096×64: verify WᵀW = I_{64}
- Wide matrix 64×4096: verify W Wᵀ = I_{64}
- Gain = 0.5: verify singular values all equal 0.5
- Reproducibility: same seed → bit-identical output
