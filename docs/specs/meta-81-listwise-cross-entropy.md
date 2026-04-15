# META-81 — Listwise Cross-Entropy (ListNet Top-1)

## Overview
**Category:** Listwise ranking loss (Plackett-Luce top-1 cross-entropy)
**Extension file:** `listwise_cross_entropy.cpp`
**Replaces/improves:** Pairwise META-20/21/22 losses when a probabilistic listwise interpretation is desired and graded labels can be normalised to a target distribution; cheaper than META-76/77/78/79 (O(n) vs O(n²))
**Expected speedup:** ≥10x over PyTorch reference (`allRank.losses.listNet`)
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n, target weights y ∈ ℝ_{≥0}^n (e.g. 2^label − 1 or graded relevance)
Output: scalar loss L (cross-entropy between top-1 score-distribution and top-1 label-distribution)

# Plackett-Luce top-1 distributions (Cao et al. 2007 §4.2):
P_y(i) = y_i / Σ_j y_j                                    # target top-1 distribution
P_f(i) = exp(s_i) / Σ_j exp(s_j)                          # model top-1 distribution (softmax)

L = − Σ_{i=1..n}  P_y(i) · log P_f(i)                     # cross-entropy

# Gradient (closed form):
∂L/∂s_k = P_f(k) − P_y(k)                                  # standard softmax-CE result
```
- Time complexity: O(n) per query (one softmax pass + one dot product)
- Space complexity: O(n)
- Property: convex in scores; minimised when P_f ≡ P_y; recovers ListMLE if the target is a one-hot at the most-relevant item

## Academic source
**Cao, Z., Qin, T., Liu, T.-Y., Tsai, M.-F., Li, H. (2007).** "Learning to rank: from pairwise approach to listwise approach." *Proc. 24th ICML*, pp. 129-136. DOI: `10.1145/1273496.1273513`.

## C++ Interface (pybind11)
```cpp
void listwise_cross_entropy(
    const float* scores, const float* target_weights, int n,
    float* out_loss,
    float* out_grad_scores               // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <8 MB (n ≤ 10000 candidates per query, batch ≤ 64 queries)
- Disk: <1 MB
- Allocation: thread-local scratch of size n holds intermediate softmax denominator and per-item P_f values

## Performance target
- Python baseline: `allRank.losses.listNet` (PyTorch with autograd)
- Target: ≥10x faster (eliminates autograd, fuses softmax + CE + grad in one pass)
- Benchmark: batch=32 × n ∈ {100, 1000, 10000}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores and target weights (any NaN target → loss=0, gradient=0; any NaN score → ValueError), double accumulator for both softmax denominator (Σ exp) and target normaliser (Σ y) — float catastrophic cancellation possible when Σ y ≈ 0, log-sum-exp shift mandatory for the score-side softmax (subtract max(s) before exp to prevent overflow), `noexcept` destructors, no `std::function` in kernel, special-case Σ y = 0 returns loss=0 (degenerate target, not an error), SIMD softmax kernel uses `_mm256_zeroupper()`, log P_f computed as `(s_i − max_s) − log(Σ exp(s_j − max_s))` (no separate division/log of P_f to preserve precision in the tail).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_81.py` | Loss and gradient match allRank/PyTorch within 1e-5 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥10x faster than PyTorch |
| 5 | Edge cases | n=1 (loss=0), all-equal scores + uniform target (loss=log n − log n = 0), all-zero target (loss=0), score=1e6 (no overflow) pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Inline log-sum-exp helper (shared with META-72 OMD entropic, META-78 NeuralNDCG)
- None external

## Pipeline stage (non-conflict)
**Owns:** Plackett-Luce top-1 listwise cross-entropy slot
**Alternative to:** META-76 ApproxNDCG, META-77 LambdaLoss, META-78 NeuralNDCG, META-79 SoftRank, META-80 Smooth-AP
**Coexists with:** META-20/21/22 pairwise losses (different family — can be combined as multi-task), META-04 coordinate ascent

## Test plan
- All-equal scores + uniform target: P_f = P_y = (1/n)·𝟙 → loss = log n − log n = 0
- One-hot target at item i*: minimised when s_{i*} dominates → loss → 0 as s_{i*} → +∞
- All-zero target weights: returns loss=0, gradient=0 (no preferred ordering)
- Large scores (1e6): log-sum-exp shift prevents overflow, output stays finite
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-4
