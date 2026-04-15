# FR-130 — Submodular Coverage Reranking

## Overview
Many diversification objectives (set cover, facility location, maximum marginal relevance) belong to the class of *submodular* functions: adding an item to a smaller set provides at least as much marginal benefit as adding it to a larger set ("diminishing returns"). Lin & Bilmes (2011) showed that a single submodular framework subsumes most extractive-summarisation diversity methods, and that greedy maximisation gives a `(1 - 1/e)` approximation guarantee. On a forum, this gives a unified, mathematically-clean diversifier with monotone increasing marginal-coverage value. Complements FR-126/127/128 because submodular coverage allows operators to compose multiple diversity sub-objectives (topic, time, author) as a sum of submodular functions, all greedy-optimisable together.

## Academic source
**Lin, H., & Bilmes, J. (2011).** "A Class of Submodular Functions for Document Summarization." *Proceedings of the 49th Annual Meeting of the Association for Computational Linguistics: Human Language Technologies (ACL-HLT 2011)*, Portland, OR, pages 510-520. (No DOI; ACL anthology paper.)

(Greedy submodular maximisation guarantee: **Nemhauser, G. L., Wolsey, L. A., & Fisher, M. L. (1978).** "An analysis of approximations for maximizing submodular set functions." *Mathematical Programming*, 14(1), 265-294. DOI: `10.1007/BF01588971`.)

## Formula
From Lin & Bilmes (2011), Eq. 4 (the combined coverage + diversity objective) and Nemhauser et al. (1978) for the greedy guarantee:

```
F(S) = α · L(S) + (1 - α) · R(S)                              (Eq. 4)

L(S) = Σ_{i ∈ V}  min( Σ_{j ∈ S}  w_{ij},  α · Σ_{j ∈ V}  w_{ij} )    (coverage)
R(S) = Σ_{k=1}^{K}  (1/|P_k|) · √( Σ_{j ∈ S ∩ P_k}  rel_j )           (diversity reward)

Where:
    V             = universe of all candidate documents
    S ⊆ V         = currently selected slate
    w_{ij}        ∈ ℝ_{≥0}, similarity (e.g. cosine) between docs i and j
    α ∈ (0,1)     = saturation parameter (paper default 0.5) — caps how much one document
                    can contribute to the coverage term
    P_1,...,P_K   = partition of V into clusters (e.g. k-means on embeddings)
    rel_j         ∈ ℝ_{≥0}, relevance of doc j to the host

Greedy maximisation (Nemhauser-Wolsey-Fisher):
    S ← ∅
    for k = 1..K_target:
        d* ← argmax_{d ∉ S}  F(S ∪ {d}) - F(S)
        S ← S ∪ {d*}
```

Both L and R are submodular and monotone non-decreasing (paper Theorem 1 and 2). Their non-negative weighted sum is also submodular and monotone, so the greedy algorithm gives a `(1 - 1/e) ≈ 0.63` approximation to the optimum (Nemhauser et al. 1978 Theorem 4.2).

## Starting weight preset
```python
"submodular_coverage.enabled": "true",
"submodular_coverage.ranking_weight": "0.0",
"submodular_coverage.alpha_saturation": "0.5",
"submodular_coverage.coverage_diversity_mix": "0.5",
"submodular_coverage.cluster_count_K": "10",
"submodular_coverage.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/submodular_coverage.cpp`
- Entry: `std::vector<int> submodular_pick(const float* sim_matrix, const float* relevance, const int* cluster_ids, int n_candidates, int n_clusters, int target_k, float alpha, float mix)`
- Complexity: O(K · n · n) for naive recomputation; lazy-greedy (Minoux 1978) reduces to expected O(K · n · log n) with priority queue
- Thread-safety: stateless; lazy-greedy with `std::priority_queue<float>` of upper-bound marginal gains
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/submodular_coverage.py::submodular_pick` — NumPy implementation with optional lazy-greedy.

## Benchmark plan
| Candidates × clusters | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 5) | 5 | <0.1 ms | <2 ms |
| medium (500 × 10) | 10 | <2 ms | <30 ms |
| large (5000 × 50) | 20 | <80 ms | <1.5 s |

## Diagnostics
- Per-position marginal-gain log in suggestion detail UI (`submodular_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `coverage_progression`, `diversity_progression`, `final_objective_value`, `lazy_greedy_recomputation_count`, `cluster_assignment_per_pick`

## Edge cases & neutral fallback
- All similarities zero → coverage term is identically zero; falls back to pure diversity-reward ranking; flag
- Single cluster (K=1) → diversity term collapses to relevance-only top-K; flag
- α = 0 → only diversity reward (degenerate); flag
- α = 1 → only coverage (degenerate); flag
- NaN/Inf in inputs → clamp; flag

## Minimum-data threshold
n ≥ 2K AND at least 2 non-empty clusters; otherwise skip.

## Budget
Disk: <2 MB  ·  RAM: <60 MB at n=5000 (similarity matrix in float32 = 100 MB → use upper triangle only, ~50 MB; plus relevance and cluster vectors)

## Scope boundary vs existing signals
- **FR-126/127/128**: aspect-based diversification with explicit aspect taxonomy; submodular coverage works on continuous similarity + cluster partition.
- **FR-129 DPP**: DPP is a special submodular function (log-det) with the volume interpretation; FR-130 admits *any* monotone submodular function so operators can compose multiple diversity criteria.
- **FR-015 final-slate diversity reranking**: pairwise MMR is a non-submodular heuristic; FR-130's framework gives the same intuition with provable approximation guarantees.

## Test plan bullets
- correctness test: paper's Section 4 toy example (synthetic 5-doc, 2-cluster set) → greedy picks match paper's Table 2 trace within 1e-6
- submodularity test: F(A ∪ {x}) − F(A) ≥ F(B ∪ {x}) − F(B) for all A ⊆ B, x ∉ B (verify on 100 random subsets)
- approximation-bound test: brute-force optimum on small instances → greedy score ≥ (1 - 1/e) · OPT
- lazy-greedy parity test: lazy-greedy result equals naive greedy result exactly (lazy-greedy is exact, just faster)
- parity test: C++ vs Python within 1e-6
- no-crash on adversarial input: zero similarities, single cluster, K > n, NaN inputs
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: tie-breaking by lower index → identical slate across runs
