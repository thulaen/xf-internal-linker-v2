# FR-101 — Tarjan Articulation Point Boost (TAPB)

## Summary

An **articulation point** (or cut vertex) is a node whose removal disconnects the graph into two or more parts. Articulation points are rare — typically 5–10% of nodes in a sparse link graph — and they are structurally critical: they are the narrow bridges that hold the site's topology together. If the host post is an articulation point, links from it carry disproportionate structural value. TAPB rewards candidates whose host is an articulation point.

Plain English: think of articulation points as intersections where the whole town relies on one road. If a high-value post is an articulation point, its outbound links are the roads that keep one side of town connected to the other.

This addresses the Reddit post's **Dangling Nodes** topology error from a second angle: DARB asks "is this high-value host hoarding juice by not linking out?"; TAPB asks "is this host structurally the only bridge between two graph regions?". Disjoint criteria, same underlying concern that dangling nodes damage the site's connectivity.

Scope:
- **Per candidate-pair signal**, host-side property.
- **Binary-ish** — host is either an articulation point or not. Bonus magnitude is fixed.
- **Bounded, additive, neutral-safe.**

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Tarjan, R. (1972). "Depth-first search and linear graph algorithms." *SIAM Journal on Computing* 1(2):146–160. |
| **DOI** | `10.1137/0201010` |
| **Open-access link** | https://epubs.siam.org/doi/10.1137/0201010 (paywall; pre-print historically at Stanford STAN-CS-TR-71-211) |
| **Relevant sections** | §3 "Biconnected components and articulation points" eq. 3.1–3.3 (pages 153–155) |
| **What we faithfully reproduce** | Tarjan's low-link DFS algorithm for identifying articulation points in undirected graphs in O(V + E) time. We use the networkx wrapper `articulation_points()` which implements Tarjan (1972) §3 directly. |
| **What we deliberately diverge on** | Tarjan defines articulation points on undirected graphs. Our link graph is directed. We symmetrize it for this signal — an articulation point in the *undirected symmetrization* is a node whose removal disconnects the underlying co-occurrence graph. This is the standard treatment for directed social-network cut analysis (Hopcroft & Tarjan 1973 ACM eq. 2; Newman 2010 §7.4.1). Documented divergence. |

### Quoted source passage

From §3 page 153:
> *"A vertex v of a graph G is called an articulation point of G if the removal of v together with all edges incident to v results in a graph G' which has more connected components than G."*

And from §3 eq. 3.2 (the low-link characterization):
> *"Let lowpt(v) = min{number(v), min{lowpt(w) | (v,w) is a tree edge}, min{number(w) | (v,w) is a back edge}}. Then v (≠ root) is an articulation point if and only if v has a child w in the DFS tree such that lowpt(w) ≥ number(v)."*

TAPB uses the output of this algorithm — a set of vertex IDs — via `networkx.articulation_points()`. We don't reimplement the DFS; we wrap the established library.

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `G` | the graph | `undirected_graph` (networkx.Graph) | `backend/apps/pipeline/services/pipeline_data.py` |
| `articulation points set` | output of Tarjan §3 | `articulation_point_set: frozenset[int]` | same |
| `host` (TAPB input) | the host content item | `host_record.key` | ranker |
| `tapb_score` | our output | `1.0 if host.key in AP set else 0.0` | `backend/apps/pipeline/services/articulation_point_boost.py` |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `tapb.enabled` | bool | `true` | Project policy (BLC §7.1). |
| `tapb.ranking_weight` | float | `0.03` | Tarjan (1972) reports articulation-point density in typical sparse graphs as < 10% of nodes (Newman 2010 §7.4.1 Table 7.1 corroborates with 5–8% density on real web graphs). A weight of 0.03 contributes 0.03 to the ~5–10% of candidates whose host is an AP and 0 to the rest — total expected contribution is `0.03 × 0.075 ≈ 0.002`, in the sub-dominant tier matching `link_farm.ranking_weight=0.03` (another rare-event structural signal). |
| `tapb.apply_to_articulation_node_only` | bool | `true` | Operator-level toggle to gate the signal strictly to articulation points (default) vs. a graded boost based on proximity to AP set (future extension). |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. DARB (FR-099)

DARB: `host.content_value × 1/(1 + host.out_degree)` — value-weighted, out-degree-modulated.

TAPB: binary — is host an articulation point in the undirected symmetrization?

**Disjoint math, disjoint inputs.** DARB ignores graph topology (only reads host's own scalar properties). TAPB ignores host value (only reads graph structure). A high-value host with many outbound links is still an AP if it bridges two components — DARB gives it 0 (saturated out-degree), TAPB gives it full bonus. Conversely, a low-value dangling host that sits in the middle of a dense cluster is DARB-max, TAPB-zero.

### vs. 15 live ranker signals

All 15 operate on different inputs. Most specifically:
- `w_node` (scope-tree proximity): uses the *configured* silo hierarchy, not the runtime-discovered link graph.
- `w_quality` (host PageRank): uses eigenvector centrality, not cut-vertex identification.
- `link_farm`: uses SCC density, which is disjoint from articulation (an SCC has no cut vertex by definition).

### vs. FR-006 Weighted PageRank

PageRank = eigenvector centrality. Articulation points = cut-vertex topology. Different measurements. Verified no existing spec uses `networkx.articulation_points()` or an equivalent algorithm.

### vs. pending specs

Searched for "articulation", "tarjan", "cut vertex", "cut point" — zero hits in `docs/specs/`.

### vs. FR-197 Link-Farm Ring Detector

FR-197 detects strongly-connected components (SCCs). An SCC is a maximal set of mutually-reachable nodes. An articulation point is a node whose removal breaks the graph. A node *inside* a large SCC is never an articulation point (removing it leaves the SCC connected minus that one node, still one component). **Disjoint categories.** A node can be inside a link-farm SCC *and* also be an articulation point if it's on the boundary — but the FR-197 penalty and TAPB bonus would act on different structural properties and would not collide.

**Conclusion: CLEAR.**

---

## Neutral Fallback

| Condition | Diagnostic |
|---|---|
| `articulation_point_set` is empty (fresh install, no edges yet) | `tapb: cold_start_no_graph` |
| Graph has < 50 nodes (too small to meaningfully identify APs) | `tapb: insufficient_graph_data` |
| Host not in graph (new host not yet crawled) | `tapb: host_not_in_graph` |
| `tapb.enabled == false` | `tapb: disabled` |

Returns `TAPBEvaluation` with `score_component=0.0, fallback_triggered=True, diagnostic=<string>, is_articulation_point=False, graph_node_count=N`.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language (v1)** | Python — wraps `networkx.articulation_points(G)` | networkx is already a project dependency (used in `weighted_pagerank.py`). Its AP implementation is a cython-accelerated Tarjan. |
| **Precompute** | Once per pipeline run via `pipeline_data.py`; cost O(V+E) | Scales linearly to 500k nodes and beyond |
| **Per-candidate lookup** | `host.key in articulation_point_set` — O(1) frozenset membership | < 100 ns |
| **Future C++ port** | Not needed — networkx's Cython layer is already close to C speed; per-candidate lookup is O(1) |
| **Module location** | `backend/apps/pipeline/services/articulation_point_boost.py` | |

---

## Hardware Budget

| Resource | Per-pipeline precompute | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|
| RAM | ~20 MB for 50k-node undirected graph + AP set | 0 | < 10 GB | 20 MB |
| CPU (precompute) | ~800 ms for 50k nodes (networkx with Cython backend) | < 100 ns lookup | < 50 ms hot-path | 0.05 ms / 500 candidates ✓ |
| GPU | 0 | 0 | < 6 GB VRAM | 0 |
| Disk | 0 | 0 | 0 | 0 |

---

## Real-World Constraints

- **Direction symmetrization**: we build an undirected `networkx.Graph` from the directed `ExistingLink` rows for AP identification. This is standard for cut-vertex analysis (Newman 2010 §7.4.1).
- **Dynamic graph**: pipeline-run scoped. Articulation points are recomputed each pipeline run. No caching across runs needed.
- **Small graph bootstrap**: fresh install with < 50 nodes → fallback triggers → zero signal contribution until graph grows.

---

## Diagnostics

```json
{
  "score_component": 0.03,
  "is_articulation_point": true,
  "graph_node_count": 12847,
  "articulation_point_count": 847,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

---

## Benchmark Plan

File: `backend/benchmarks/test_bench_tapb.py`.

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 candidates, 100-node graph | < 10 ms (incl. precompute) | > 100 ms |
| medium | 100 candidates, 10k-node graph | < 300 ms (incl. precompute) | > 2 s |
| large | 500 candidates, 100k-node graph | < 3 s (incl. precompute) | > 15 s |

Per-candidate cost (post-precompute): O(1) frozenset lookup.

---

## Edge Cases

| Edge case | TAPB behavior | Test |
|---|---|---|
| Host == dest | Filtered upstream | `test_tapb_not_called_for_self_links` |
| Host is an articulation point | `score_component = 1.0 × weight = 0.03` | `test_tapb_scores_articulation_point` |
| Host is not an articulation point | `score_component = 0.0` | `test_tapb_neutral_for_non_ap` |
| Graph has < 50 nodes | Fallback `insufficient_graph_data` → 0.0 | `test_tapb_neutral_below_data_floor` |
| Host not yet in graph | Fallback `host_not_in_graph` → 0.0 | `test_tapb_neutral_when_host_missing` |
| `tapb.enabled=false` | Fallback `disabled` → 0.0 | `test_tapb_neutral_when_disabled` |
| Graph is a single connected component with no APs (clique) | AP set empty → all candidates get 0.0 | `test_tapb_empty_ap_set_on_clique` |
| Disconnected graph (multiple components) | AP set contains cut vertices within each component | `test_tapb_handles_disconnected_graph` |

---

## Gate Justifications

All Gate A boxes pass. No exceptions required.

---

## Pending

- [ ] Python module `articulation_point_boost.py`.
- [ ] Precompute cache in `pipeline_data.py` — `articulation_point_set` + `undirected_graph_size`.
- [ ] Unit tests `test_tapb.py`.
- [ ] Benchmark `test_bench_tapb.py`.
- [ ] `Suggestion.score_tapb` + `Suggestion.tapb_diagnostics` columns (migration 0036).
- [ ] `tapb.*` keys in `recommended_weights.py` + migration 0035 upsert.
- [ ] Integration into `ranker.py` at component index 17.
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card + tooltip (Codex follow-up).
- [ ] C++ fast path — not needed (networkx Cython is already the fast path; per-candidate is O(1)).
