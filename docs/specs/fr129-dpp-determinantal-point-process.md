# FR-129 — DPP (Determinantal Point Process) Diversification

## Overview
IA-Select / xQuAD / PM2 (FR-126/127/128) need an explicit aspect taxonomy. When the host page's sub-topics are not classifiable into discrete aspects, an aspect-free diversification method is needed. DPPs (Determinantal Point Processes) achieve diversity through a probabilistic model where the probability of a subset is proportional to the determinant of its kernel-similarity submatrix — geometrically, the squared *volume* spanned by the items' feature vectors. Picking high-volume subsets naturally selects items that point in different directions in feature space. Complements FR-126/127/128 because DPPs need no aspect taxonomy, only an item-similarity kernel that we already compute.

## Academic source
**Kulesza, A., & Taskar, B. (2012).** "Determinantal Point Processes for Machine Learning." *Foundations and Trends in Machine Learning*, 5(2-3), 123-286. DOI: `10.1561/2200000044`. (Also published as a monograph on arXiv: `arXiv:1207.6083`.)

(Greedy-MAP DPP inference for top-K selection: **Chen, L., Zhang, G., & Zhou, E. (2018).** "Fast Greedy MAP Inference for Determinantal Point Process to Improve Recommendation Diversity." *Advances in Neural Information Processing Systems 31 (NeurIPS 2018)*. arXiv: `1709.05135`.)

## Formula
From Kulesza & Taskar (2012), Eq. 2.1 (the DPP probability) and Chen et al. (2018), Algorithm 1 (greedy MAP):

```
DPP probability of subset Y ⊆ [n]:
    P(Y; L) = det(L_Y) / det(L + I)                                (Eq. 2.1)

Where L is an n × n positive-semidefinite L-ensemble kernel:
    L_{ij} = q_i · q_j · S_{ij}

    q_i = √(relevance score of item i)
    S_{ij} = similarity between items i and j (e.g. cosine of feature vectors)
    L_Y = principal submatrix of L indexed by Y

Greedy MAP DPP (Chen et al. 2018, Alg. 1, log-det maximisation):
    Y ← ∅; c_i ← 0 for all i; d_i^2 ← L_{ii}
    for k = 1..K:
        j* = argmax_{i ∉ Y}  log(d_i^2)
        Y ← Y ∪ {j*}
        for each i ∉ Y:
            e_i = (L_{j*,i} - <c_{j*}, c_i>) / d_{j*}
            c_i ← [c_i; e_i]                  (append e_i to vector c_i)
            d_i^2 ← d_i^2 - e_i^2
```

The Cholesky-style update keeps the algorithm at O(K² · n) instead of the naive O(K · n · K³) determinant recomputation. Chen et al. Theorem 1 shows greedy MAP is a `(1 - 1/e)` approximation to the optimal subset-MAP problem.

## Starting weight preset
```python
"dpp.enabled": "true",
"dpp.ranking_weight": "0.0",
"dpp.kernel_source": "semantic_embedding_cosine",
"dpp.relevance_weight_alpha": "1.0",
"dpp.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/dpp.cpp`
- Entry: `std::vector<int> dpp_greedy_map(const float* L_kernel, int n_candidates, int target_k)` where `L_kernel` is row-major n×n PSD matrix
- Complexity: O(K² · n) using Chen et al. Cholesky-update algorithm; for K=10, n=500 this is 50,000 ops
- Thread-safety: stateless; SIMD over the inner-product `<c_{j*}, c_i>` step using AVX2
- Numerical safety: clamp `d_i^2` to ≥ 1e-12 before logarithm; abort to fallback if non-PSD detected (negative `d_i^2`)
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/dpp.py::dpp_greedy_map` — NumPy implementation following Chen et al. Algorithm 1 verbatim.

## Benchmark plan
| Candidates | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50) | 5 | <0.1 ms | <2 ms |
| medium (500) | 10 | <2 ms | <30 ms |
| large (5000) | 20 | <80 ms | <1.2 s |

## Diagnostics
- Per-position log-determinant gain in suggestion detail UI (`dpp_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `kernel_source`, `final_log_determinant`, `marginal_log_det_per_pick`, `effective_dimension` (rank estimate of L_Y), `relevance_alpha_used`

## Edge cases & neutral fallback
- Non-PSD kernel (negative eigenvalue from numerical noise) → project onto PSD cone via eigendecomposition with negative eigenvalues set to 0; flag `kernel_psd_repair`
- Zero candidates → empty slate
- All-identical candidates (rank-1 L) → DPP picks only 1 item (det = 0 for K ≥ 2); flag and pad with relevance-ranked fallback
- NaN/Inf in kernel → clamp; flag
- `K > rank(L)` → warn and truncate K to rank

## Minimum-data threshold
n ≥ 2K AND kernel must be at least rank-2; otherwise skip diversification.

## Budget
Disk: <2 MB  ·  RAM: <50 MB at n=5000 (kernel matrix in float32 = 100 MB if stored, but we only need the upper triangle and column-wise access → 50 MB with packed storage)

## Scope boundary vs existing signals
- **FR-126/127/128**: aspect-based; DPP is aspect-free, uses only the similarity kernel.
- **FR-015 final-slate diversity reranking**: pairwise dissimilarity (often MMR-style); DPP uses set-level determinant which captures *joint* diversity, not pairwise.
- **FR-014 near-duplicate clustering**: hard deduplication; DPP gives a soft, continuous-volume diversity measure.
- **FR-130 submodular coverage**: submodular objective is a different mathematical class from DPP; DPP is a special-case submodular function but with the determinant-volume interpretation.

## Test plan bullets
- correctness test: 3-item toy with known L kernel → greedy MAP picks match Chen et al. Table 1 within 1e-6
- volume-monotonicity test: log-det of selected subset is non-decreasing per pick (greedy property)
- approximation-bound test: brute-force log-det MAP on small instances → greedy ≥ (1 - 1/e) · OPT
- parity test: C++ vs Python within 1e-6
- PSD-repair test: synthetic kernel with one negative eigenvalue (-1e-4) → repair makes it PSD without flipping ranking
- no-crash on adversarial input: rank-1 kernel, zero candidates, K > n, NaN kernel entries
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: tie-breaking by lower index → identical slate across runs
