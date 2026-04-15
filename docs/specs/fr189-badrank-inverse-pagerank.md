# FR-189 — BadRank Inverse-PageRank

## Overview
BadRank is the cleanest formulation of "guilt by association": run PageRank on the **reverse** link graph using a known-spam seed vector. Hosts that are reachable only from spam (so they show up high on the reverse-PR vector) are themselves likely spam or low-trust. Unlike SpamRank (FR-188), BadRank uses no per-page bias term — it's a pure inverse-PR computation, which makes it cheap to run and easy to audit. Complements `fr188-spamrank-propagation` because BadRank is the parameter-free baseline against which SpamRank's bias-weighted variant is judged.

## Academic source
Full citation: **Sobek, M. (2002).** "BadRank as the Opposite of PageRank." Self-published technical note, *Pr0.net*. Archived at the Wayback Machine. Subsequently formalised in **Wu, B. & Davison, B. D. (2005).** "Identifying link farm spam pages." In *Proceedings of the 14th International Conference on the World Wide Web (WWW '05) — Special Interest Tracks and Posters*, pp. 820-829. DOI: `10.1145/1062745.1062762`.

## Formula
Sobek (2002): swap link direction and replace uniform teleport with a spam-seed teleport vector. The recurrence is the standard PageRank fixed point on the transposed graph:

```
BR(x) = (1 − d) · s(x)
      + d · Σ_{y ∈ N⁺(x)} BR(y) / |N⁻(y)|

where
  d        = damping factor, fixed at 0.85
  s(x)     = 1 / |S| if x ∈ S (spam seed set), 0 otherwise
  N⁺(x)   = outbound link set of x (now treated as inbound on reverse graph)
  N⁻(y)   = inbound link set of y (now treated as outbound on reverse graph)
```

Equivalently: `BR = PageRank(G^T, teleport = s)`. The reverse-direction summation is what makes pages that *link to* spam (as opposed to receiving links from spam) score high.

## Starting weight preset
```python
"badrank.enabled": "true",
"badrank.ranking_weight": "0.0",
"badrank.damping": "0.85",
"badrank.max_iterations": "50",
"badrank.seed_size": "500",
```

## C++ implementation
- File: `backend/extensions/badrank.cpp`
- Entry: `std::vector<double> badrank(const CSRGraph& host_graph_transposed, const std::vector<int>& spam_seeds, double d, int max_iter)`
- Complexity: O(I · (N + E))
- Thread-safety: pure; reuses the SpMV kernel from FR-186 on the transposed graph
- SIMD: AVX2 SpMV
- Builds via pybind11; transposed CSR cached separately from forward graph

## Python fallback
`backend/apps/pipeline/services/badrank.py::compute_badrank` using `scipy.sparse.csr_matrix.transpose()` and biased power iteration.

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 0.5 ms | 25 ms |
| Medium | 5,000 | 30 ms | 1.6 s |
| Large | 100,000 | 850 ms | 65 s |

## Diagnostics
- Per-host BadRank score (e.g. "BR: 0.0009")
- Inverse `1 − normalize(BR)` used as ranker contribution
- C++/Python badge
- Fallback flag when seed set empty
- Debug fields: `n_spam_seeds`, `iterations_used`, `seed_overlap_with_spamrank`

## Edge cases & neutral fallback
- Empty spam seed set → neutral 0.5 for all hosts, fallback flag set
- Host with no outbound links → never accumulates bad mass, stays at floor
- Pure spam seed retains `s(x) = 1/|S|`
- Disconnected from any spam seed → BR ≈ teleport floor

## Minimum-data threshold
At least 100 known spam seeds and ≥ 1,000 hosts in graph before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 1.5 MB  ·  RAM: 9 MB per 100k hosts (forward + transposed CSR)

## Scope boundary vs existing signals
Distinct from `fr188-spamrank-propagation` (adds per-page bias term, different propagation kernel) and from `fr187-host-trustrank` (positive seeds, forward graph). BadRank is the parameter-free pure inverse-PR formulation against which SpamRank is the augmented variant.

## Test plan bullets
- Unit: page A → spam_seed returns high BR for A
- Unit: page disconnected from seed returns BR ≈ teleport floor
- Parity: C++ vs Python on 5,000-host fixture within 1e-6
- Parity: BadRank on transposed graph equals reverse-PR with seed teleport
- Edge: empty seed set returns neutral 0.5 with fallback flag
- Integration: `1 − normalize(BR)` contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
