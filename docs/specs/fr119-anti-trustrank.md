# FR-119 — Anti-TrustRank

## Overview
The mirror of FR-118. Some forum pages are known-bad: spam threads, deleted-but-still-indexed posts, low-quality auto-generated content, mod-flagged listings. Anti-TrustRank starts from these bad seeds and propagates *distrust* through the link graph along the same biased-PageRank machinery. Pages with high distrust mass are demoted as link destinations. Complements FR-118 by giving operators a symmetric "negative seed" mechanism — without it, TrustRank can only reward, never penalise. Together the two scores form a trust-vs-distrust differential that is more robust than either alone.

## Academic source
**Krishnan, V., & Raj, R. (2006).** "Web Spam Detection with Anti-Trust Rank." *Proceedings of the 2nd International Workshop on Adversarial Information Retrieval on the Web (AIRWeb 2006)*, Seattle, WA, pages 37-40. (No DOI; AIRWeb workshop paper.)

## Formula
Krishnan & Raj (2006) propose running biased PageRank on the *transposed* graph (because distrust flows from spam pages backwards along inbound links to pages that link to them):

```
at_{k+1} = α · Tᵀ · at_k + (1 - α) · b                (Eq. 1, transposed propagation)

Where:
    at ∈ ℝⁿ     = anti-trust score vector
    Tᵀ ∈ ℝⁿˣⁿ   = transposed transition matrix (Tᵀ[i,j] = 1/in_degree(j) if i→j)
    b ∈ ℝⁿ      = bad-seed vector, b[i] = 1/|B| if i ∈ B (known-bad), else 0
    α ∈ (0,1)   = damping factor, paper default 0.85
    |B|         = number of bad seed pages

Final score (paper Section 3.3):
    distrust(p) = at(p)
    trust_minus_distrust(p) = trust(p) - λ · distrust(p)     (paper experiments use λ = 1.0)
```

Iterate until `‖at_{k+1} - at_k‖₁ < ε`. Convergence guaranteed for `α < 1`.

## Starting weight preset
```python
"anti_trustrank.enabled": "true",
"anti_trustrank.ranking_weight": "0.0",
"anti_trustrank.damping": "0.85",
"anti_trustrank.max_iterations": "100",
"anti_trustrank.convergence_tolerance": "1e-7",
"anti_trustrank.distrust_lambda": "1.0",
"anti_trustrank.bad_seed_source": "moderator_flags",
```

## C++ implementation
- File: `backend/extensions/anti_trustrank.cpp` (shares the SpMV kernel with `trustrank.cpp` via templated `backend/extensions/biased_pagerank_kernel.hpp` parameterised on `transpose: bool`)
- Entry: `std::vector<float> anti_trustrank(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, const int* bad_seeds, int n_bad, float damping, int max_iter, float tol)`
- Complexity: O(k · |E|) per iteration with transposed sparse SpMV
- Thread-safety: stateless; same SIMD pattern as FR-118
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/anti_trustrank.py::compute_anti_trustrank` using `networkx.pagerank(G.reverse(copy=False), personalization=bad_seed_dict)` which gives the equivalent transposed-graph biased PageRank.

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges, 10 bad seeds) | <10 ms | <80 ms |
| medium (10K nodes, 100K edges, 50 bad seeds) | <120 ms | <1.2 s |
| large (100K nodes, 1.5M edges, 200 bad seeds) | <2.5 s | <30 s |

## Diagnostics
- Raw distrust value in suggestion detail UI (`anti_trustrank_diagnostics.distrust_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `convergence_iterations`, `bad_seed_count`, `nearest_bad_seed_hops`, `trust_minus_distrust_combined`, `final_l1_delta`

## Edge cases & neutral fallback
- Zero bad seeds → distrust = 0 everywhere → neutral 0.5, flag `neutral_no_bad_seeds`
- Destination cannot reach any bad seed via the transposed graph → distrust = 0 → score 1.0 (clean), but only if FR-118 also returned a non-neutral trust score; otherwise neutral 0.5
- Convergence failure → fallback 0.5
- Dangling-source handling on transposed graph: redistribute uniformly
- NaN/Inf clamping

## Minimum-data threshold
≥ 1 bad seed configured before the signal goes live; otherwise neutral 0.5.

## Budget
Disk: <1 MB additional (kernel shared with FR-118)  ·  RAM: <80 MB for a 100K-node graph

## Scope boundary vs existing signals
- **FR-118 TrustRank**: positive propagation from good seeds; anti-TrustRank is the negative-side propagation from bad seeds on the transposed graph. The two are symmetric and combined as `trust − λ · distrust`.
- **FR-006 weighted PageRank**: no notion of bad seeds; cannot demote spam-adjacent pages.
- **FR-021 Pixie random walk**: per-query proximity, not a global distrust signal.

## Test plan bullets
- convergence test: 8-node toy graph from Krishnan & Raj (2006) Section 4 → distrust scores match paper Table 2 within 1e-4
- transpose-equivalence test: anti-TrustRank on G equals TrustRank on `G.reverse()` with same seeds within 1e-6
- parity test: C++ vs Python within 1e-5
- combined-score test: `trust − λ·distrust` ranking matches paper's Section 4 demotion behaviour on a labelled spam corpus
- no-crash on adversarial input: bad-seed equals every node, bad-seed isolated, transposed self-loops
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical input → identical scores
