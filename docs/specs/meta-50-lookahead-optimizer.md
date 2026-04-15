# META-50 — Lookahead Optimizer Wrapper

## Overview
**Category:** Optimizer wrapper (slow-fast weight averaging around any inner optimizer)
**Extension file:** `lookahead.cpp`
**Replaces/improves:** Stand-alone use of META-34 Adam, META-46–53; Lookahead reduces variance and improves generalisation by interpolating slow weights toward k-step inner trajectory
**Expected speedup:** ≥4x over PyTorch `torch_optimizer.Lookahead` Python wrapper step
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm
```
Input: φ_0 ∈ ℝ^d (slow weights), inner optimizer A (e.g. Adam), step k, slow lr α ∈ (0,1] (typ. 0.5)
State: θ_0 = φ_0 (fast weights)

for outer = 1..M:
    for inner = 1..k:
        θ ← A.step(θ, ∇f(θ))                    # k inner fast updates
    φ ← φ + α · (θ − φ)                          # slow-weight interpolation (Zhang 2019 eq. 1)
    θ ← φ                                        # reset fast weights to slow
```
- Time complexity: O(M · k · cost(A.step)) + O(M · d) overhead
- Space complexity: O(d) extra for slow weights φ
- Convergence: Zhang et al. 2019 Thm 1: variance of fast weights bounded; quadratic convergence to optimum on quadratic loss

## Academic source
**Zhang, M. R., Lucas, J., Hinton, G., & Ba, J. (2019).** "Lookahead optimizer: k steps forward, 1 step back." *Advances in Neural Information Processing Systems* (NeurIPS), 32. URL: `https://papers.nips.cc/paper_files/paper/2019/hash/90fd4f88f588ae64038134f1eeaa023f`. arXiv: `1907.08610`.

## C++ Interface (pybind11)
```cpp
// Lookahead wrapper: holds slow weights phi and resets fast theta every k inner steps
struct Lookahead {
    std::vector<double> phi;
    int k;
    double alpha;
    int inner_count;

    void slow_update(double* theta, int d);   // every k calls applies phi update + theta reset
};

void lookahead_step(
    double* theta, double* phi, int* inner_count,
    int d, int k, double alpha
);
```

## Memory budget
- Runtime RAM: <16 MB (d ≤ 1M → 8 MB φ + 8 MB θ)
- Disk: <1 MB
- Allocation: aligned 64-byte `std::vector<double>` for φ; SIMD interpolation `φ + α·(θ − φ)`

## Performance target
- Python baseline: `torch_optimizer.Lookahead` outer step
- Target: ≥4x faster (excluding inner optimizer cost)
- Benchmark: d ∈ {1k, 100k, 1M}, 100 outer × 5 inner steps

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 fused-multiply-add for interpolation with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on θ and φ, `noexcept` destructors, k ≥ 1 and α ∈ (0,1] guards, no `std::function` in slow-update loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_50.py` | Matches `torch_optimizer.Lookahead` within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than reference |
| 5 | Edge cases | k=1 (no lookahead) / α=1 (full sync) / NaN / d=1M pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (single-threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Any inner optimizer: META-34 Adam, META-46–49, META-51–53

## Pipeline stage (non-conflict)
**Owns:** outer-loop weight-averaging slot
**Alternative to:** none — wraps another optimizer rather than competing for the inner slot
**Coexists with:** META-34 Adam (inner), META-46–53 (inner), META-54 GP-EI HPO over k, α

## Test plan
- Wrapping Adam on Rosenbrock: lower variance trajectory than bare Adam
- k=1, α=1: behaviourally identical to inner optimizer (verify)
- α=0: φ never moves (verify)
- NaN in θ: raises `ValueError`
- d=1M, 100 outer steps: meets target time
