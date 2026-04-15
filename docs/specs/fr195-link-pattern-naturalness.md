# FR-195 — Link-Pattern Naturalness

## Overview
Natural editorial link graphs follow well-studied scale-free statistics: the bow-tie macro-structure, power-law degree distributions, and small triangle counts relative to k-cliques. Spam link patterns deviate sharply: rings, stars, fully-connected cliques, and perfect wheels are vanishingly rare in organic graphs. Detecting these unnatural sub-structures around a host gives a robust topology-only spam signal. Complements `fr188-spamrank-propagation` because SpamRank propagates penalty from labelled seeds, while naturalness flags structural anomalies even with no spam seeds available.

## Academic source
Full citation: **Broder, A., Kumar, R., Maghoul, F., Raghavan, P., Rajagopalan, S., Stata, R., Tomkins, A., & Wiener, J. (2000).** "Graph structure in the web." In *Proceedings of the 9th International World Wide Web Conference (WWW9)*, pp. 309-320. DOI: `10.1145/371920.371965`. The bow-tie macro-structure and power-law expectations from this paper define the "natural" baseline against which spam sub-structures are measured. Anomaly templates (rings, stars, cliques, wheels) extend the framework following the link-farm taxonomy in **Wu & Davison (2005)**, "Identifying link farm spam pages," WWW 2005.

## Formula
Broder et al. (2000), Section 3: define a finite set of pattern templates `P = {ring, star, clique_k, wheel}` and the per-host expected probability under the natural bow-tie + power-law null model. For each candidate sub-graph `S` around host `H`:

```
naturalness(H) = 1 − max_{P ∈ {ring, star, clique_k, wheel}}  P(S | unnatural-pattern_P)

where
  P(S | unnatural-pattern_P)
    = #{ matches of template P in 2-hop neighbourhood of H }
      / expected_count(P | natural bow-tie null model)

expected_count(P | natural)
    = ⌈ N · α_P · (k̄ / N)^|E(P)| ⌉            (Broder et al., Eq. 3)

  N  = number of nodes in 2-hop neighbourhood
  k̄  = mean degree
  |E(P)| = edge count of pattern P
  α_P  = pattern-specific normalisation constant
         (ring = 1, star = 1, clique_k = k!, wheel = k)
```

Pattern templates:

```
ring(k):    cycle of length k with no chords, k ≥ 5
star(k):    one centre connected to k leaves, no inter-leaf edges
clique_k:   complete graph K_k, k ≥ 4
wheel(k):   star(k) + outer cycle on the k leaves
```

Final ranker contribution: `naturalness(H)` directly (high = natural, low = unnatural).

## Starting weight preset
```python
"link_naturalness.enabled": "true",
"link_naturalness.ranking_weight": "0.0",
"link_naturalness.min_clique_k": "4",
"link_naturalness.min_ring_k": "5",
"link_naturalness.neighbourhood_hops": "2",
```

## C++ implementation
- File: `backend/extensions/link_naturalness.cpp`
- Entry: `double link_naturalness(const CSRGraph& host_graph, int host_id, const NaturalnessParams& p)`
- Complexity: O(d² + d_clique^k) where d = degree of H; capped at d ≤ 200 for tractability
- Thread-safety: pure on input slice; per-host computation independent
- SIMD: AVX2 bitset intersection for clique enumeration
- Builds via pybind11; uses an arena allocator for transient k-tuple sets

## Python fallback
`backend/apps/pipeline/services/link_naturalness.py::compute_link_naturalness` using `networkx.cycle_basis`, `networkx.find_cliques`, and explicit star/wheel matchers.

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 2 ms | 100 ms |
| Medium | 5,000 | 100 ms | 6 s |
| Large | 100,000 | 3 s | ~4 min |

## Diagnostics
- Per-host naturalness value (e.g. "Naturalness: 0.18 — clique_5 detected (×3)")
- Detected pattern types and counts
- C++/Python badge
- Fallback flag when degree exceeds tractability cap
- Debug fields: `degree`, `n_rings`, `n_stars`, `n_cliques`, `n_wheels`, `dominant_pattern`

## Edge cases & neutral fallback
- Host with degree < 5 → neutral 0.5 (insufficient structure to evaluate)
- Host with degree > 200 → cap at 200 random sample of neighbours; fallback flag set
- Disconnected host → naturalness = 1.0 (no patterns to detect, treated as natural)
- Pattern overlap (e.g. wheel contains star) — count only the most-specific match

## Minimum-data threshold
Host must have at least 5 inbound or outbound host edges before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 1.0 MB  ·  RAM: 12 MB peak (k-tuple bitsets during clique enumeration)

## Scope boundary vs existing signals
Distinct from `fr188-spamrank-propagation` (label propagation from seeds), `fr189-badrank-inverse-pagerank` (inverse-PR), and `fr194-host-cluster-cohesion` (raw intra-vs-inter edge ratio). Link-pattern naturalness is a topology-only motif-counting signal that operates without labelled seeds and without per-host PR computation.

## Test plan bullets
- Unit: 5-clique returns naturalness near 0
- Unit: 6-ring returns low naturalness
- Unit: scale-free Barabasi-Albert subgraph returns naturalness near 1.0
- Parity: C++ vs Python on 5,000-host fixture within 1e-6
- Edge: degree-3 host returns neutral 0.5 with fallback flag
- Edge: degree > 200 capped with random sample, fallback flag set
- Integration: naturalness contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
