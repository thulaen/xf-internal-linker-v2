# FR-117 — HITS Hub Score

## Overview
The complement to FR-116. On a forum, hub pages are roundup posts, "best of" stickies, FAQ indexes, and guide-pages whose value comes from pointing at many good authorities. When the linker proposes a candidate destination, knowing the *host* page's hub score tells us whether the host is a hub-style page (suggesting we should add many high-quality outbound links) or an authority-style page (where outbound links should be sparse and pointed). Complements FR-116 because the two scores are produced by the same eigenvector iteration but applied to different ranking decisions: authority on destination, hub on host.

## Academic source
**Kleinberg, J. M. (1999).** "Authoritative sources in a hyperlinked environment." *Journal of the ACM*, 46(5), 604-632. DOI: `10.1145/324133.324140`.

## Formula
Hub score is the second of the two mutually-recursive HITS quantities. From Kleinberg (1999), Eq. O:

```
h(p) = Σ_{q : p→q} a(q)              (hub = sum of authorities you point at)

In matrix form, hub is the principal eigenvector of A · Aᵀ:
    h_{k+1} = A · (Aᵀ · h_k)

Equivalent two-step update:
    a_{k+1} = Aᵀ · h_k
    h_{k+1} = A   · a_{k+1}
    h_{k+1} ← h_{k+1} / ‖h_{k+1}‖₂
```

Where `A` is the n×n adjacency of the topic-induced subgraph, `h ∈ ℝⁿ` initialised to the uniform vector `1/√n`. By Perron-Frobenius, `h` converges to the principal eigenvector of `AAᵀ` whose eigenvalue equals that of `AᵀA` (so authority and hub iterations converge in lock-step).

## Starting weight preset
```python
"hits_hub.enabled": "true",
"hits_hub.ranking_weight": "0.0",
"hits_hub.subgraph_size": "200",
"hits_hub.max_iterations": "50",
"hits_hub.convergence_tolerance": "1e-6",
```

## C++ implementation
- File: `backend/extensions/hits_hub.cpp` (shares the iteration kernel with `hits_authority.cpp` via a templated header `backend/extensions/hits_kernel.hpp`)
- Entry: `std::vector<float> hits_hub(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int max_iter, float tol)`
- Complexity: O(k · |E|) per iteration; same SpMV kernel as FR-116, just returns the second vector
- Thread-safety: stateless; reuses the FR-116 kernel and L2 normalisation via `cblas_snrm2`
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/hits_hub.py::compute_hub_scores` using `networkx.hits` (returns `(hubs, authorities)` tuple, take the first element).

## Benchmark plan
| Subgraph size | C++ target | Python target |
|---|---|---|
| small (50 nodes, 200 edges) | <2 ms | <15 ms |
| medium (500 nodes, 4K edges) | <25 ms | <250 ms |
| large (5K nodes, 50K edges) | <300 ms | <4 s |

## Diagnostics
- Raw hub value in suggestion detail UI (`hits_hub_diagnostics.hub_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `convergence_iterations`, `host_out_degree`, `subgraph_node_count`, `co_score_authority` (because we computed both, expose the destination's authority too for free)

## Edge cases & neutral fallback
- Host has no outbound edges → neutral 0.5, flag `neutral_no_outlinks`
- Disconnected subgraph → run on connected component; singleton → neutral 0.5
- Convergence failure → fallback 0.5, flag
- NaN/Inf clamping per iteration
- Self-loops removed before iteration

## Minimum-data threshold
Host page must have ≥ 5 outbound edges in the topic-induced subgraph; otherwise neutral 0.5.

## Budget
Disk: <1 MB additional (kernel shared with FR-116)  ·  RAM: <50 MB for a 5K-node subgraph

## Scope boundary vs existing signals
- **FR-116 HITS authority**: same eigenvector iteration but the authority score scores destinations; the hub score scores hosts. Different role in the suggestion pair.
- **FR-006 weighted PageRank**: PageRank gives a single role-agnostic centrality. HITS hub explicitly says "this page is good *because of* its outbound choices."
- **FR-021 Pixie random walk**: Pixie measures personalised proximity, not the host's hub-like character.

## Test plan bullets
- convergence test: 4-node bipartite toy → hub scores match Kleinberg (1999) Fig. 1 within 1e-4
- parity test: C++ vs Python on 100-node random graph within 1e-4
- co-computation test: hub iteration emits the same authority vector as FR-116 (must be byte-identical when using the shared kernel)
- no-crash on adversarial input: dangling-out nodes, self-loops, parallel edges
- integration test: `ranking_weight = 0.0` leaves final ordering unchanged
- determinism: identical edge list → identical scores
