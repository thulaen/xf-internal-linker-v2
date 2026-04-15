# FR-120 — SALSA (Stochastic Approach for Link-Structure Analysis)

## Overview
HITS (FR-116/117) is sensitive to "tightly knit community" effects where a small clique of mutually-linked pages dominates both authority and hub scores. SALSA fixes this by running two separate random walks (one on the bipartite hub graph, one on the bipartite authority graph) instead of mutually reinforcing eigenvectors. On a forum, this means a clique of cross-linked spam threads cannot inflate each other's scores the way they can with HITS. Complements FR-116 because SALSA is the spam-resistant successor to HITS using the same hub/authority concept but a stochastic-matrix formulation.

## Academic source
**Lempel, R., & Moran, S. (2000).** "The Stochastic Approach for Link-Structure Analysis (SALSA) and the TKC Effect." *Proceedings of the 9th International World Wide Web Conference (WWW9)*, Amsterdam, pages 387-401. DOI: `10.1016/S1389-1286(00)00034-7` (Computer Networks journal version).

## Formula
SALSA constructs a bipartite undirected graph from the directed adjacency, then runs two independent random walks. From Lempel & Moran (2000), Section 3:

```
Bipartite graph: nodes split into H = hub-side copies, A = authority-side copies.
Edge (h_i, a_j) exists iff i → j in original directed graph.

Authority score (Eq. 7):
    a(j) = Σ_{i : (h_i,a_j) ∈ E}  1 / (in_degree(j) · out_degree(i))

Hub score (Eq. 6):
    h(i) = Σ_{j : (h_i,a_j) ∈ E}  1 / (out_degree(i) · in_degree(j))

Equivalently, for each connected component C of the bipartite graph:
    a(j) = in_degree(j) / Σ_{k ∈ C ∩ A} in_degree(k)
    h(i) = out_degree(i) / Σ_{k ∈ C ∩ H} out_degree(k)
```

Where in/out degrees are computed on the original directed graph. This closed-form solution (Theorem 1 in the paper) means SALSA does *not* require power iteration — it is a single pass over the bipartite components.

## Starting weight preset
```python
"salsa.enabled": "true",
"salsa.ranking_weight": "0.0",
"salsa.subgraph_size": "200",
"salsa.score_axis": "authority",
```

## C++ implementation
- File: `backend/extensions/salsa.cpp`
- Entry: `std::vector<float> salsa(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int score_axis)` where `score_axis ∈ {0=hub, 1=authority}`
- Complexity: O(|V| + |E|) total — single union-find pass to identify connected components, then one degree-sum pass per component
- Thread-safety: stateless; union-find with path compression + union-by-rank
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/salsa.py::compute_salsa_scores` using `networkx.connected_components` on the bipartite expansion plus per-component degree normalisation.

## Benchmark plan
| Subgraph size | C++ target | Python target |
|---|---|---|
| small (50 nodes, 200 edges) | <0.5 ms | <8 ms |
| medium (500 nodes, 4K edges) | <8 ms | <100 ms |
| large (5K nodes, 50K edges) | <100 ms | <1.5 s |

## Diagnostics
- Raw SALSA value in suggestion detail UI (`salsa_diagnostics.salsa_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `score_axis`, `component_size` (size of bipartite component containing destination), `component_count`, `node_in_degree`, `node_out_degree`

## Edge cases & neutral fallback
- Singleton bipartite component (destination is isolated) → neutral 0.5, flag `neutral_isolated_in_bipartite`
- Zero in-degree (authority axis) or zero out-degree (hub axis) → score = 0, mapped to neutral 0.5 with flag
- Disconnected directed graph → handled naturally by per-component normalisation; no special case
- NaN/Inf impossible (closed-form ratio of positive integers); guard anyway

## Minimum-data threshold
Bipartite component containing the destination must have ≥ 5 authority-side nodes; otherwise neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <30 MB for a 5K-node subgraph (union-find arrays + degree vectors in int32)

## Scope boundary vs existing signals
- **FR-116/117 HITS**: HITS uses mutually-reinforcing eigenvectors which suffer the TKC (tightly-knit community) effect; SALSA's bipartite random-walk formulation is provably TKC-resistant (Lempel & Moran Theorem 5).
- **FR-006 weighted PageRank**: PageRank is a global random walk on the directed graph; SALSA is two separate walks on the bipartite expansion.
- **FR-118 TrustRank**: orthogonal — TrustRank biases by seed set, SALSA is unbiased.

## Test plan bullets
- TKC-resistance test: paper's Figure 3 adversarial graph (one tight clique + one larger loose community) → SALSA gives loose-community node higher authority than HITS does (matches paper's Table 1 within 1e-4)
- closed-form parity test: closed-form per-component ratio matches stationary distribution of explicit random walk on the bipartite expansion within 1e-6
- C++ vs Python parity within 1e-5
- no-crash on adversarial input: complete bipartite K_{n,n}, single edge, all-self-loops (which produce zero edges in bipartite expansion)
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: union-find with deterministic tie-breaking → identical scores across runs
