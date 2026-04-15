# FR-186 — Site-Level PageRank

## Overview
Standard PageRank operates on individual pages, but two pages on the same host often share authority that page-level PageRank double-counts. Collapsing every URL on a host into a single super-node and running PageRank on the resulting host graph yields a per-host authority score. Forum threads on a high-authority host inherit a stronger prior than threads on a no-name domain, even when the page-level PageRank is identical. Complements `fr033-internal-pagerank-heatmap` because page-level PR measures intra-site authority while site-level PR captures inter-host authority transferred by the broader link economy.

## Academic source
Full citation: **Bharat, K. & Henzinger, M. R. (1998).** "Improved algorithms for topic distillation in a hyperlinked environment." In *Proceedings of the 21st Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '98)*, pp. 104-111. DOI: `10.1145/290941.291009`. Section 4.2 introduces the host-collapsed graph used to dampen self-promotional intra-host link clusters.

## Formula
Bharat & Henzinger (1998), Section 4.2: collapse all pages in host `H` into a single super-node; the host-graph PageRank is then a fixed-point of the standard PageRank recurrence applied to the collapsed graph:

```
PR_host(H) = (1 − d) / N_hosts
           + d · Σ_{H' → H} PR_host(H') / L_out(H')

where
  d         = damping factor, fixed at 0.85
  N_hosts   = total number of distinct hosts in the graph
  H' → H    = host-graph edge from H' to H (any page-page edge across host boundaries)
  L_out(H') = number of distinct outbound host neighbours of H'
```

Self-loops (intra-host links) are removed before iteration; this is the key correction over naive page-level PR.

## Starting weight preset
```python
"site_pagerank.enabled": "true",
"site_pagerank.ranking_weight": "0.0",
"site_pagerank.damping": "0.85",
"site_pagerank.max_iterations": "100",
"site_pagerank.convergence_tol": "1e-6",
```

## C++ implementation
- File: `backend/extensions/site_pagerank.cpp`
- Entry: `std::vector<double> site_pagerank(const CSRGraph& host_graph, double d, int max_iter, double tol)`
- Complexity: O(I · (N_hosts + E_hosts)) where I = iteration count
- Thread-safety: read-only on input graph; per-iteration vector double-buffered
- SIMD: AVX2 fused multiply-add on the per-iteration sparse SpMV
- Builds via pybind11; reuses `CSRGraph` shared with FR-033

## Python fallback
`backend/apps/pipeline/services/site_pagerank.py::compute_site_pagerank` using `scipy.sparse` CSR matrices and power iteration.

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 0.5 ms | 25 ms |
| Medium | 5,000 | 30 ms | 1.5 s |
| Large | 100,000 | 800 ms | 60 s |

## Diagnostics
- Per-host PR value displayed on suggestion detail (e.g. "Site PR: 0.0042")
- Convergence iteration count
- C++/Python badge
- Fallback flag when host graph not yet built
- Debug fields: `n_hosts`, `n_host_edges`, `iterations_used`, `final_delta`

## Edge cases & neutral fallback
- Single-host graph → neutral 0.5 (no inter-host structure)
- Disconnected component containing host → trapped at teleport floor `(1−d)/N`
- Host with zero outbound links → leaks; redistribute uniformly per Brin & Page
- New host with no inlinks yet → floor at `(1−d)/N`

## Minimum-data threshold
At least 50 distinct hosts in the graph before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 1.5 MB  ·  RAM: 8 MB per 100k hosts (double-precision PR vectors)

## Scope boundary vs existing signals
Does not duplicate `fr033-internal-pagerank-heatmap` (page-level PR) or `fr037-silo-connectivity-leakage-map` (silo connectivity). Site-level PR operates on a graph where every host is one node; page-level PR operates on a graph where every URL is one node — different objects, different semantics.

## Test plan bullets
- Unit: 3-host triangle returns equal PR ≈ 1/3 each
- Unit: hub host with 10 inbound hosts ranks above leaves
- Parity: C++ vs Python on 5,000-host fixture within 1e-6
- Edge: dangling host correctly redistributed
- Edge: single-host graph returns neutral 0.5 with fallback flag
- Integration: site PR contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
