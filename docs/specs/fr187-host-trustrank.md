# FR-187 — Host-Level TrustRank

## Overview
TrustRank propagates trust from a small hand-picked seed of known-good hosts through the link graph using biased PageRank. Hosts that receive link mass primarily from trusted seeds inherit high trust; hosts that sit far from any seed receive almost none. Run at the host level (not page level) it gives a robust per-domain trust prior that resists individual-page manipulation. Complements `fr188-spamrank-propagation` because TrustRank is the white-list dual of SpamRank's black-list propagation.

## Academic source
Full citation: **Gyöngyi, Z., Garcia-Molina, H., & Pedersen, J. (2004).** "Combating web spam with TrustRank." In *Proceedings of the 30th International Conference on Very Large Data Bases (VLDB '04)*, pp. 576-587. Morgan Kaufmann.

## Formula
Gyöngyi et al. (2004), Section 4.2: replace the uniform teleport vector in PageRank with a non-uniform seed vector `d`, normalised so trust mass is conserved:

```
TR(H) = (1 − α) · d(H)
      + α · Σ_{H' → H} TR(H') / L_out(H')

where
  α      = damping factor, fixed at 0.85
  d(H)   = 1 / |S| if H ∈ S (seed set), 0 otherwise
  S      = hand-picked trusted host set, |S| typically 200-2000
  H' → H = host-graph inbound edge
```

Inverse-PageRank is run first to choose the seed set: pick hosts with highest reverse-PR to maximise downstream trust coverage (Section 3.3).

## Starting weight preset
```python
"host_trustrank.enabled": "true",
"host_trustrank.ranking_weight": "0.0",
"host_trustrank.damping": "0.85",
"host_trustrank.seed_size": "200",
"host_trustrank.max_iterations": "50",
```

## C++ implementation
- File: `backend/extensions/host_trustrank.cpp`
- Entry: `std::vector<double> host_trustrank(const CSRGraph& host_graph, const std::vector<int>& seeds, double alpha, int max_iter)`
- Complexity: O(I · (N + E))
- Thread-safety: pure on input graph; double-buffered iteration vector
- SIMD: AVX2 SpMV; mask-blend for seed teleport
- Builds via pybind11; shares `CSRGraph` with FR-186

## Python fallback
`backend/apps/pipeline/services/host_trustrank.py::compute_host_trustrank` using `scipy.sparse` and power iteration with sparse seed teleport.

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 0.6 ms | 30 ms |
| Medium | 5,000 | 35 ms | 1.8 s |
| Large | 100,000 | 900 ms | 70 s |

## Diagnostics
- Per-host TrustRank value (e.g. "TR: 0.018")
- Distance to nearest seed (graph hops)
- C++/Python badge
- Fallback flag when seed set empty
- Debug fields: `n_seeds`, `iterations_used`, `seed_coverage_pct`

## Edge cases & neutral fallback
- Empty seed set → neutral 0.5 for all hosts, fallback flag set
- Host disconnected from any seed → TR ≈ 0; floor at `1e-9` for log-display
- Seed host receives self-trust = 1/|S| as initial mass
- Seed selection re-runs only when host graph delta > 5%

## Minimum-data threshold
At least 50 hand-picked trusted seeds and ≥ 500 hosts in graph before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 1.5 MB  ·  RAM: 8 MB per 100k hosts

## Scope boundary vs existing signals
Distinct from `fr186-site-level-pagerank` (uniform teleport, no trust seeding) and from `fr188-spamrank-propagation` (propagates penalty from spam seeds, not trust from good seeds). TrustRank is the positive-seeded biased PageRank.

## Test plan bullets
- Unit: 3-host chain seed→A→B→C returns monotonically decreasing TR
- Unit: trusted seed retains highest TR
- Parity: C++ vs Python on 5,000-host fixture within 1e-6
- Edge: empty seed list returns neutral 0.5 with fallback flag
- Edge: isolated host has TR = 0, displayed as `1e-9`
- Integration: TR contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
