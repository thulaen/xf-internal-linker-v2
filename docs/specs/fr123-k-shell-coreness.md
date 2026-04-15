# FR-123 — K-Shell Coreness

## Overview
Eigenvector-based centralities (PageRank, HITS, Katz) reward pages with influential neighbours but can over-weight a hub-with-one-neighbour pattern. K-shell decomposition instead asks "what is the densest subgraph this node belongs to?" — a node's coreness is the largest k such that it survives in the k-core (subgraph where every node has degree ≥ k). On a forum this surfaces destinations embedded in a thick conversation cluster (e.g. a long-running megathread referenced by hundreds of cross-linked posts) rather than destinations that happen to be linked from one big hub. Complements FR-006/116/122 because coreness is a *combinatorial* density measure, not a spectral one — Kitsak et al. (2010) showed it is the strongest predictor of true influence in many real networks, often beating PageRank and betweenness.

## Academic source
**Kitsak, M., Gallos, L. K., Havlin, S., Liljeros, F., Muchnik, L., Stanley, H. E., & Makse, H. A. (2010).** "Identification of influential spreaders in complex networks." *Nature Physics*, 6(11), 888-893. DOI: `10.1038/nphys1746`.

(Original k-core decomposition algorithm: Seidman, S. B. (1983). "Network structure and minimum degree." *Social Networks*, 5(3), 269-287. DOI: `10.1016/0378-8733(83)90028-X`.)

## Formula
From Seidman (1983) and the linear-time algorithm of Batagelj & Zaveršnik (2003):

```
k-core(G, k) = maximal subgraph H ⊆ G such that every node in H has
               degree_H(v) ≥ k

coreness(v) = max { k : v ∈ k-core(G, k) }

Algorithm (Batagelj & Zaveršnik 2003, O(|E|)):
    sort vertices by degree
    while ∃ v with current degree < target k:
        coreness(v) ← k - 1
        remove v from G
        decrement degrees of v's neighbours
    increment k and repeat
```

For undirected graphs the construction is unique. For our directed forum graph we operate on the underlying undirected graph (Kitsak et al. follow this convention; Section "Methods").

Influence prediction (Kitsak Eq. 1, k_S-based ranking):
```
influence_predicted(v) ∝ coreness(v)
```

## Starting weight preset
```python
"k_shell.enabled": "true",
"k_shell.ranking_weight": "0.0",
"k_shell.directionality": "undirected",
"k_shell.normalisation": "max_coreness",
```

## C++ implementation
- File: `backend/extensions/k_shell.cpp`
- Entry: `std::vector<int> k_shell_coreness(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int directionality)` where `directionality ∈ {0=undirected, 1=in_degree, 2=out_degree}`
- Complexity: O(|V| + |E|) total — Batagelj-Zaveršnik with bucket-sort by degree. Single-pass, no power iteration.
- Thread-safety: stateless; bucket-array degree management with O(1) updates
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/k_shell.py::compute_coreness` using `networkx.core_number(G)` (which implements Batagelj-Zaveršnik internally).

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges) | <0.5 ms | <8 ms |
| medium (10K nodes, 100K edges) | <8 ms | <120 ms |
| large (100K nodes, 1.5M edges) | <120 ms | <2 s |

## Diagnostics
- Raw coreness integer in suggestion detail UI (`k_shell_diagnostics.coreness`)
- Normalised score `coreness / max_coreness` in `[0, 1]`
- C++/Python badge
- Fallback flag
- Signal-specific fields: `coreness_value` (raw int), `max_coreness_in_graph`, `peer_count_at_same_coreness`, `directionality_used`

## Edge cases & neutral fallback
- Isolated node (degree 0) → coreness = 0 → mapped to neutral 0.5, flag `neutral_isolated_node`
- All-zeros graph (no edges) → all coreness = 0 → all destinations neutral 0.5
- Self-loops: undirected k-shell ignores them (paper convention) — strip before decomposition
- No NaN/Inf risk (integer arithmetic only); guard the normalisation divisor against zero

## Minimum-data threshold
Graph must have at least one edge and `max_coreness ≥ 1`; otherwise neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <40 MB for a 100K-node graph (degree array + bucket array + neighbour CSR in int32)

## Scope boundary vs existing signals
- **FR-006 weighted PageRank**: PageRank is spectral and continuous; coreness is combinatorial and integer-valued. Kitsak et al. (2010) Figure 2 shows they correlate but disagree on the "long tail" of influence — coreness is more robust to noise.
- **FR-116/117 HITS**: HITS gives smooth eigenvector scores; coreness gives integer shells. A node can have high coreness but low HITS authority (e.g. dense local cluster, no global hubs pointing in).
- **FR-122 Katz**: Katz counts walks; coreness counts surviving-degree under iterative pruning. Independent axes.
- **FR-098 dominant passage centrality**: intra-document; coreness is inter-document.

## Test plan bullets
- correctness test: paper's Figure 1 toy graph (k-shell decomposition of a small social network) → coreness values match Kitsak et al. exactly (integer equality, no tolerance)
- monotonicity test: removing an edge cannot increase any node's coreness (paper Lemma 1)
- parity test: C++ vs `networkx.core_number` exact integer equality on a 1000-node Erdős-Rényi graph
- no-crash on adversarial input: complete graph K_n (all coreness = n-1), star graph (centre coreness = 1, leaves = 1), disconnected pieces, self-loops
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list → identical coreness (the algorithm is deterministic given a stable node ordering)
