# META-78 — NeuralNDCG Listwise Loss

## Overview
**Category:** Listwise ranking loss (NeuralSort-based differentiable NDCG)
**Extension file:** `neural_ndcg.cpp`
**Replaces/improves:** META-76 ApproxNDCG when a strict-permutation-matrix relaxation is preferred over per-pair sigmoid smoothing — NeuralSort produces a row-stochastic "soft permutation" with a single global temperature τ
**Expected speedup:** ≥5x over PyTorch reference (`allRank` library)
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n for one query, relevance labels y ∈ ℕ^n, temperature τ > 0
Output: differentiable NDCG approximation in [0, 1]

# 1. NeuralSort (Grover et al. 2019) — soft permutation matrix P̂ ∈ ℝ^{n×n}     # Pobrotyn 2021 §3
A_s = | s ⊗ 𝟙 − 𝟙 ⊗ s |                           # n × n abs-difference matrix
for i = 1..n:
    P̂[i, :] = softmax( ((n + 1 − 2i) · s − A_s · 𝟙) / τ )
# Each row of P̂ is a probability distribution over which item is ranked at position i

# 2. Use P̂ to compute the expected NDCG
gain = 2^y − 1                                                                 # n-vector
sorted_gain_soft = P̂ · gain                                                    # expected gain at each rank
discount = [1 / log_2(1 + i) for i in 1..n]                                    # n-vector

DCG_neural = sorted_gain_soft · discount
IDCG       = compute_ideal_dcg(y)
neural_ndcg = DCG_neural / IDCG
loss        = 1 − neural_ndcg
```
- Time complexity: O(n²) for A_s and the softmax-row scan; O(n²) for the matvec
- Space complexity: O(n²) for A_s and P̂
- Property: as τ → 0⁺, P̂ → exact permutation matrix and NeuralNDCG → exact NDCG; differentiable through softmax for any τ > 0

## Academic source
**Pobrotyn, P., Białobrzeski, R. (2021).** "NeuralNDCG: direct optimisation of a ranking metric via differentiable relaxation of sorting." *arXiv:2102.07831*. Builds on Grover et al. (2019) "Stochastic optimization of sorting networks via continuous relaxations," *ICLR*.

## C++ Interface (pybind11)
```cpp
void neural_ndcg(
    const float* scores, const int* labels, int n,
    float tau,
    int truncation_k,                  // 0 = full NDCG, k > 0 = top-k discount mask
    float* out_loss,
    float* out_grad_scores             // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <20 MB (n ≤ 500 → 1 MB for P̂ matrix in float, plus scratch; batch ≤ 32 queries via thread-local arena)
- Disk: <1 MB
- Allocation: thread-local arena holds A_s and P̂ (both n × n) reused per query in the batch

## Performance target
- Python baseline: `allRank` PyTorch implementation
- Target: ≥5x faster (analytic gradient + fused softmax-rowscan kernel)
- Benchmark: batch=16 × n ∈ {50, 200, 500}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores and τ (τ ≤ 0 → ValueError), double accumulator for the per-row softmax normaliser (Σ exp(·) over n terms — use log-sum-exp shift to prevent overflow), `noexcept` destructors, no `std::function` in inner softmax-row loop, P̂ matrix not materialised when only the loss is needed (fuse matvec inside the row-softmax loop), backward pass implemented analytically (∂P̂[i,k]/∂s_j derived once on paper), SIMD softmax kernel uses `_mm256_zeroupper()`, IDCG cached per query, `(n + 1 − 2i)·s` precomputed once per row.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_78.py` | Loss and gradient match allRank within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than allRank |
| 5 | Edge cases | n=1, all-equal scores (P̂ = uniform), τ=1e-3, τ=10, all-zero labels pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Inline log-sum-exp helper (shared with META-72 OMD entropic projection)
- META-77 LambdaLoss (shares IDCG and 2^y precomputation routines)

## Pipeline stage (non-conflict)
**Owns:** NeuralSort-based listwise NDCG-surrogate slot
**Alternative to:** META-76 ApproxNDCG (per-pair sigmoid), META-77 LambdaLoss (metric-bound), META-79 SoftRank (Gaussian-noise relaxation)
**Coexists with:** META-20/21/22 pairwise losses, META-81 listwise cross-entropy

## Test plan
- Single relevant doc at top: loss → 0 (within 1e-3) for τ ≤ 0.1
- All-equal scores: P̂ = (1/n)·𝟙𝟙ᵀ (uniform rows); loss reflects unsorted DCG
- All-equal labels: IDCG = 0 → loss = 0
- τ → 0⁺: NeuralNDCG matches exact NDCG within 1e-3 (τ = 1e-3 in practice)
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-3
