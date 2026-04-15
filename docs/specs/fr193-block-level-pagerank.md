# FR-193 — Block-Level PageRank

## Overview
Vanilla PageRank treats every link on a page as equally important. Block-level PageRank exploits the fact that real web pages decompose into visual blocks (sidebar, footer, main body) and that links inside the main body carry more authority than links in chrome. Computing PR in two stages — first within each block, then across blocks weighted by block importance — yields a more faithful authority distribution than flat PR. Complements `fr033-internal-pagerank-heatmap` because the heatmap visualises page-level PR while block-level PR is the upstream computation that yields more accurate per-page scores.

## Academic source
Full citation: **Kamvar, S. D., Haveliwala, T. H., Manning, C. D., & Golub, G. H. (2003).** "Exploiting the block structure of the web for computing PageRank." In *Proceedings of the 12th International World Wide Web Conference (WWW '03)*. DOI: `10.1145/775152.775153`. The companion VLDB-style writeup, **Cai et al. (2004)**, extends the framework to visual block segmentation (VIPS).

## Formula
Kamvar et al. (2003), Section 3: a two-stage decomposition where local PR is computed inside each block, then aggregated transition probabilities are used for cross-block PR:

```
Stage 1 — local PageRank inside each block b:

  PR_local(p | b) = (1 − d) / |b|
                  + d · Σ_{q ∈ b, q → p} PR_local(q | b) / L_out_b(q)

Stage 2 — block-level PageRank across blocks:

  PR_block(b) = (1 − d) / N_blocks
              + d · Σ_{b' → b} PR_block(b') · T(b', b)

  where T(b', b) = Σ_{q ∈ b'} π(q | b') · (#{q → p ∈ b} / L_out(q))
                 (aggregated transition from b' to b under stationary
                  distribution π inside b')

Stage 3 — final per-page PageRank:

  PR(p) = PR_block(b_p) · PR_local(p | b_p)

where
  d         = damping factor, fixed at 0.85
  b_p       = the block containing page p
  L_out_b(q) = outdegree of q restricted to edges staying in block b
  L_out(q)  = total outdegree of q across the entire graph
```

Convergence is provably faster than flat PR when the block structure matches the link graph (Kamvar Theorem 3).

## Starting weight preset
```python
"block_pagerank.enabled": "true",
"block_pagerank.ranking_weight": "0.0",
"block_pagerank.damping": "0.85",
"block_pagerank.block_unit": "host",
"block_pagerank.max_iterations": "100",
```

## C++ implementation
- File: `backend/extensions/block_pagerank.cpp`
- Entry: `std::vector<double> block_pagerank(const CSRGraph& g, const std::vector<int>& page_to_block, double d, int max_iter)`
- Complexity: O(I_local · E_local + I_block · E_block) — typically 5x faster than flat PR
- Thread-safety: blocks computed in parallel via `std::for_each(par_unseq, …)`
- SIMD: AVX2 SpMV inside each local block
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/block_pagerank.py::compute_block_pagerank` using `scipy.sparse.csgraph.connected_components` to build per-block subgraphs and `numpy` for cross-block aggregation.

## Benchmark plan

| Size | Pages | C++ target | Python target |
|---|---|---|---|
| Small | 1,000 | 5 ms | 200 ms |
| Medium | 100,000 | 400 ms | 18 s |
| Large | 5,000,000 | 12 s | ~10 min |

## Diagnostics
- Per-page final PR (e.g. "PR: 0.0034 = 0.18 block × 0.019 local")
- Block size and convergence iterations per block
- C++/Python badge
- Fallback flag when block partition unavailable
- Debug fields: `block_id`, `block_size`, `pr_block`, `pr_local`, `local_iterations`, `block_iterations`

## Edge cases & neutral fallback
- Page-to-block mapping unknown → fall back to flat PageRank
- Single-block graph → equivalent to flat PR
- Empty block (no pages) → skipped in stage 1
- Block with no inter-block links → block PR floor at `(1−d)/N_blocks`

## Minimum-data threshold
At least 5 distinct blocks and ≥ 1,000 pages before signal contributes; otherwise fall back to flat PR (FR-186 / FR-033).

## Budget
Disk: 2.0 MB  ·  RAM: 16 MB per 1M pages

## Scope boundary vs existing signals
Distinct from `fr033-internal-pagerank-heatmap` (visualisation of page PR) and `fr186-site-level-pagerank` (host super-node PR with no inner-page resolution). Block-level PR is the two-stage upstream algorithm that produces faster-converging, block-aware per-page PR; it does not collapse pages into super-nodes the way FR-186 does.

## Test plan bullets
- Unit: 2-block graph returns PR matching flat PR baseline within 1e-4
- Unit: identity block partition (1 block per page) returns flat PR exactly
- Parity: C++ vs Python on 100k-page fixture within 1e-6
- Edge: empty block list returns flat PR with fallback flag
- Edge: single block matches flat PR
- Integration: PR contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
