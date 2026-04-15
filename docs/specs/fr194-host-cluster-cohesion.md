# FR-194 — Host-Cluster Cohesion

## Overview
A well-organised host has many internal links (intra-host edges) and proportionally fewer external links (inter-host edges) — its content is internally cohesive. A link farm or splog has the opposite signature: lots of outbound noise, few self-references. Measuring the cohesion ratio gives a cheap topology-only signal that distinguishes editorial sites from spam aggregators. Complements `fr037-silo-connectivity-leakage-map` because silo leakage measures how silo-correct the internal links are, while cohesion measures the raw intra-vs-inter ratio.

## Academic source
Full citation: **Eiron, N. & McCurley, K. S. (2004).** "Untangling compound documents on the web." In *Proceedings of the 27th Annual International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '04)*, pp. 472-473. DOI: `10.1145/1008992.1009091`. The full method is detailed in **Eiron, N. & McCurley, K. S. (2003).** "Locality, hierarchy, and bidirectionality on the web." In *Workshop on Web Algorithms*, IPAM. The cohesion ratio in the formula below is the operational form used in the SIGIR 2004 short paper.

## Formula
Eiron & McCurley (2004), Section 2: cohesion of host `H` is the share of edges with at least one endpoint in `H` that fall entirely inside `H`:

```
cohesion(H) = E_intra(H) / (E_intra(H) + E_inter(H))

where
  E_intra(H) = #{ (u, v) : u ∈ H ∧ v ∈ H ∧ u ≠ v }
  E_inter(H) = #{ (u, v) : (u ∈ H ⊕ v ∈ H) }
               (XOR — exactly one endpoint in H)
```

Properties:
- Pure-internal site (no outbound links): `cohesion = 1.0`
- Pure-aggregator (no internal links): `cohesion ≈ 0.0`
- Typical editorial host: `0.6 ≤ cohesion ≤ 0.9`
- Link farm: `0.1 ≤ cohesion ≤ 0.4`

## Starting weight preset
```python
"host_cohesion.enabled": "true",
"host_cohesion.ranking_weight": "0.0",
"host_cohesion.target_min": "0.50",
"host_cohesion.penalty_below": "0.30",
```

## C++ implementation
- File: `backend/extensions/host_cohesion.cpp`
- Entry: `double host_cohesion(const CSRGraph& page_graph, const std::vector<int>& page_to_host, int host_id)`
- Complexity: O(degree_sum(H)) per host — single linear scan of incident edges
- Thread-safety: read-only on input; per-host computation independent across hosts
- SIMD: AVX2 mask-compare of host-id arrays for batched same-host detection
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/host_cohesion.py::compute_host_cohesion` using `scipy.sparse` boolean masks on a `host_id`-coloured edge list.

## Benchmark plan

| Size | Pages | C++ target | Python target |
|---|---|---|---|
| Small | 1,000 | 0.5 ms | 15 ms |
| Medium | 100,000 | 30 ms | 800 ms |
| Large | 5,000,000 | 800 ms | 35 s |

## Diagnostics
- Per-host cohesion value (e.g. "Cohesion: 0.78 — 1,240 intra / 350 inter")
- Cohesion histogram across all hosts in the silo
- C++/Python badge
- Fallback flag when host has < 10 incident edges
- Debug fields: `n_intra`, `n_inter`, `host_size_pages`, `outdegree_total`

## Edge cases & neutral fallback
- Host with no incident edges → neutral 0.5, fallback flag set
- Host with only intra-edges → cohesion = 1.0
- Host with only inter-edges → cohesion = 0.0
- Self-loop edges (u = v) excluded from both numerator and denominator

## Minimum-data threshold
Host must have at least 10 incident edges (intra + inter combined) before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 0.4 MB  ·  RAM: 4 MB per 1M pages (host-id colouring vector + sparse counts)

## Scope boundary vs existing signals
Distinct from `fr037-silo-connectivity-leakage-map` (silo-correctness inside the same host) and from `fr186-site-level-pagerank` (host-graph authority propagation). Host-cluster cohesion measures only the raw intra-vs-inter edge ratio; it does not consider silos, link weights, or PR mass flow.

## Test plan bullets
- Unit: host with 100 intra and 0 inter returns 1.0
- Unit: host with 0 intra and 100 inter returns 0.0
- Unit: host with 70 intra and 30 inter returns 0.7
- Parity: C++ vs Python on 100k-page fixture within 1e-9
- Edge: host with 0 incident edges returns neutral 0.5 with fallback flag
- Edge: self-loops excluded
- Integration: cohesion contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
