# META-77 — LambdaLoss Listwise Loss

## Overview
**Category:** Listwise ranking loss (provable upper bound on ΔIR-metric × pairwise log-sigmoid)
**Extension file:** `lambda_loss.cpp`
**Replaces/improves:** Heuristic LambdaRank (which has gradients but no loss function); LambdaLoss provides a true loss with the same well-behaved gradients and a metric-driven upper bound
**Expected speedup:** ≥7x over TF-Ranking reference (`tensorflow_ranking.losses.LambdaLoss`)
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n for one query, relevance labels y ∈ ℕ^n, IR metric M (e.g. NDCG@k)
Output: scalar loss L (upper bound on Σ ΔM × log-sigmoid loss; Wang et al. 2018 Thm 1)

# 1. Compute |ΔM(i, j)| — change in metric M if items i and j swap                # Wang 2018 §3
for each pair (i, j) with y_i > y_j:
    swap_metric_delta(i, j) = | M(rank with i, j swapped) − M(rank as-is) |
    # For NDCG with positions p_i, p_j:
    ΔNDCG(i,j) = | gain_diff · disc_diff |  where
        gain_diff = (2^{y_i} − 2^{y_j}) / IDCG
        disc_diff = (1/log_2(1+p_i)) − (1/log_2(1+p_j))

# 2. LambdaLoss = − Σ_{i,j: y_i > y_j} log σ(s_i − s_j) · |ΔM(i, j)|
L = 0
for each (i, j) with y_i > y_j:
    L = L − log_sigmoid(s_i − s_j) · |ΔM(i, j)|

# 3. Gradient: same well-behaved form as LambdaRank
λ_i = Σ_{j: y_i > y_j} −σ(s_j − s_i) · |ΔM(i, j)|
       − Σ_{j: y_j > y_i} (−σ(s_i − s_j)) · |ΔM(j, i)|
return L, λ
```
- Time complexity: O(n² ) for the pair loop + O(n log n) sort once for ranks
- Space complexity: O(n)
- Property: every minimiser of LambdaLoss is a minimiser of the metric-weighted pairwise log-loss; provides the missing loss function for LambdaRank gradients (Wang 2018 Thm 1)

## Academic source
**Wang, X., Li, C., Golbandi, N., Bendersky, M., Najork, M. (2018).** "The LambdaLoss framework for ranking metric optimization." *Proc. 27th ACM CIKM*, pp. 1313-1322. DOI: `10.1145/3269206.3271784`.

## C++ Interface (pybind11)
```cpp
void lambda_loss(
    const float* scores, const int* labels, int n,
    int metric_kind,                     // 0 = NDCG, 1 = NDCG@k, 2 = ARP, 3 = ERR
    int truncation_k,
    float* out_loss,
    float* out_grad_scores               // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 1000, batch ≤ 64 queries via per-query thread-local scratch)
- Disk: <1 MB
- Allocation: thread-local arena holds rank array + Δ matrix scratch (only the upper triangle is needed)

## Performance target
- Python baseline: `tensorflow_ranking.losses.LambdaLoss`
- Target: ≥7x faster
- Benchmark: batch=32 × n ∈ {50, 200, 1000}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores/labels and on IDCG (IDCG = 0 → return loss = 0, gradient = 0), double accumulator for the pair-sum reduction, log_sigmoid implemented as `−softplus(−z)` with the numerically stable `softplus(z) = max(z, 0) + log(1 + exp(−|z|))` form, `noexcept` destructors, no `std::function` in inner pair loop, ranks computed once via `std::sort` on indices into a scratch buffer (no per-iteration allocation), SIMD pair-loop uses `_mm256_zeroupper()` after the vectorised log-sigmoid kernel, ΔNDCG computed in double precision (gain difference uses 2^y which can overflow float for y ≥ 24).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_77.py` | Loss and gradient match TF-Ranking within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥7x faster than TF-Ranking |
| 5 | Edge cases | n=1, all-equal labels (loss=0), large y_i=30, NaN score pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-76 ApproxNDCG (shares IDCG computation)
- Inline numerically-stable softplus / log_sigmoid

## Pipeline stage (non-conflict)
**Owns:** metric-bound listwise loss slot
**Alternative to:** META-76 ApproxNDCG (smooth-rank), META-78 NeuralNDCG (NeuralSort-based), META-79 SoftRank, META-80 Smooth-AP, META-81 listwise cross-entropy
**Coexists with:** META-20/21/22 pairwise losses (different loss family), META-04 coordinate ascent

## Test plan
- Random scores, monotone labels: loss decreases monotonically as scores are aligned with labels
- All-equal labels: |ΔM| = 0 for all pairs → loss = 0
- y_i = 30 (gain = 2^30 − 1): no overflow, IDCG computed in double
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-3
- NDCG@k vs full NDCG: gradients differ only for items outside top-k
