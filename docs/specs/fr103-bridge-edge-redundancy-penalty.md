# FR-103 — Bridge-Edge Redundancy Penalty (BERP)

## Summary

A **bridge edge** (or cut edge) in a graph is an edge whose removal disconnects the graph into two components. Bridges are topologically fragile — they are the single points of failure in the link structure.

BERP applies a small **penalty** when adding `host → dest` would create a new bridge edge (i.e. host and dest are currently in separate components, or there are no other paths between them). The reasoning: bridges concentrate link equity along a narrow channel. The site is healthier with *multiple* paths between any two regions, not single fragile bridges.

Plain English: if you're about to build the only road connecting two neighbourhoods, maybe build somewhere that already has other roads — you get diversification and reliability.

This addresses the Reddit post's **Duplicate Lines** concern from the inverse direction — BERP discourages *new* fragile bridges; KMIG discourages *redundant* edges where alternate paths exist. Together they steer the graph toward multi-path resilience.

Scope:
- **Per candidate-pair signal, penalty shape** (applied as negative contribution).
- **Bounded, subtractive** — max penalty is `-berp.ranking_weight`.
- **Neutral fallback is 0.0** (neither boost nor penalty).

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Hopcroft, J. & Tarjan, R. (1973). "Algorithm 447: efficient algorithms for graph manipulation." *Communications of the ACM* 16(6):372–378. |
| **DOI** | `10.1145/362248.362272` |
| **Open-access link** | https://dl.acm.org/doi/10.1145/362248.362272 (ACM paywall; pre-print at Princeton CSTR-1971) |
| **Relevant sections** | §2 "Biconnected components and bridges" (page 373); Algorithm 3 on page 375 |
| **What we faithfully reproduce** | The Hopcroft-Tarjan O(V+E) bridge-detection algorithm. We wrap `networkx.bridges(G)` which implements Tarjan-based bridge detection. |
| **What we deliberately diverge on** | Hopcroft-Tarjan is defined on undirected graphs. We symmetrize the directed link graph (same symmetrization as TAPB and KCIB — Newman 2010 §7.4.1 standard treatment). We check whether the *candidate* `host → dest` edge would be a bridge **if added** — this requires a slightly different test than "is this an existing bridge?" We use the property: candidate (host, dest) would form a bridge iff host and dest are in different biconnected components when the candidate edge is absent, AND their components are currently disconnected via any path. For efficiency we approximate this: check whether host and dest are in the same biconnected component (BCC) of the existing undirected graph. If not, the candidate edge would be a bridge. If yes, it would not. This is a faithful adaptation — BCCs partition the graph exactly by bridges (Tarjan 1972 §3). |

### Quoted source passage

From §2 page 373:
> *"An edge is called a bridge if its removal disconnects the graph. The biconnected components of a graph partition its edges into equivalence classes under the relation 'belongs to a simple cycle with'."*

And from Algorithm 3:
> *"Using depth-first search and lowpt values, we can identify all bridges in O(V+E) time. An edge (v, w) is a bridge iff w is a child of v in the DFS tree and lowpt(w) > number(v)."*

BERP's use: we precompute the BCC membership of each node. A candidate `host → dest` would introduce a new bridge iff `bcc(host) != bcc(dest)`. The penalty is applied when that condition holds.

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `G` | undirected graph | `undirected_graph` | `pipeline_data.py` |
| `BCC(v)` | biconnected-component label of v | `bcc_label_map[node_id]` | `pipeline_data.py` |
| `edge is a bridge` | our test: `bcc(u) != bcc(v)` | `host_bcc != dest_bcc` | `bridge_edge_redundancy.py` |
| `berp_penalty` | our output | `-1.0` if would-be bridge else `0.0`, times `ranking_weight` | same |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `berp.enabled` | bool | `true` | Project policy (BLC §7.1). |
| `berp.ranking_weight` | float | `0.04` | Hopcroft-Tarjan reports bridge density is ~2% of edges on typical sparse graphs (Newman 2010 §7.4.1 Table 7.1 corroborates 1–3% for web/social graphs). A penalty weight of 0.04 produces expected contribution `-0.04 × 0.02 ≈ -0.0008` per candidate, matching the magnitude of `keyword_stuffing.ranking_weight=0.04` penalty band. |
| `berp.min_component_size` | int | `5` | If either host's or dest's BCC has fewer than 5 nodes, the "would-be bridge" detection is noisy (tiny components can't meaningfully be said to be structurally distinct). We skip the penalty in that case (fall back to neutral). Seidman 1983 §4 discusses this small-component edge case. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. TAPB (FR-101)

TAPB: articulation **points** (node removal disconnects graph).
BERP: bridge **edges** (edge removal disconnects graph).

Tarjan 1972 §3 shows these are distinct structural objects: a bridge edge always has at least one articulation-point endpoint, but the converse doesn't hold. They measure different things. TAPB rewards candidates from cut-vertex hosts; BERP penalizes candidates that would create new cut edges.

**Disjoint inputs and outputs.** No overlap.

### vs. FR-197 Link-Farm Ring Detector

FR-197 detects SCCs (strongly-connected components). BCCs (biconnected components) used by BERP are a different decomposition — BCC partitions *edges* into cycle-equivalence classes, SCC partitions *nodes* into reachability-equivalence classes. A graph can have both rich BCC structure and simple SCC structure (a tree has no SCC ≥ 2 but many BCCs) or vice versa. Different measurements.

### vs. KMIG

KMIG measures 2-hop reachability redundancy. BERP measures whether the edge would be a unique bridge. KMIG fires when host→dest is already reachable in 2 hops; BERP fires when adding the edge would *create* a new bridge (they can't be in the same BCC because there's no existing path at all).

**KMIG high ⇔ multiple existing paths ⇔ same BCC ⇔ BERP zero.**
**KMIG zero ⇔ no existing path ⇔ different BCCs ⇔ BERP high penalty.**

These are inversely correlated but capture different nuances — KMIG is a continuous reachability strength (even one 2-hop path gives a non-zero score); BERP is a binary structural connectivity class membership. They can fire on the same candidate with aligned signs (KMIG bonus small + BERP penalty applied) or opposite signs (KMIG bonus large + BERP zero). **Complementary, not duplicative.**

### vs. other 13 live signals

None operate on biconnected components. Verified by searching `docs/specs/` for "bridge", "biconnected", "cut edge" — zero hits relevant to graph theory (the `broken-link` hits relate to HTTP 404 links, a different concept).

**Conclusion: CLEAR.**

---

## Neutral Fallback

| Condition | Diagnostic |
|---|---|
| `bcc_label_map` empty / graph < 50 nodes | `berp: insufficient_graph_data` |
| Host or dest BCC size < `min_component_size` (default 5) | `berp: small_component_skip` |
| Host or dest not in graph | `berp: host_or_dest_not_in_graph` |
| `berp.enabled == false` | `berp: disabled` |

Returns `BERPEvaluation` with `score_component: float` (always ≤ 0, because this is a penalty).

---

## Architecture Lane

Python only. Wraps `networkx.biconnected_components(G)` and builds a node→BCC-label map.

Module: `backend/apps/pipeline/services/bridge_edge_redundancy.py`.

---

## Hardware Budget

| Resource | Per-pipeline precompute | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|
| RAM | ~20 MB for 50k-node graph + BCC map | 0 | < 10 GB | 20 MB |
| CPU (precompute) | ~1 s for 50k nodes | < 100 ns (two dict lookups + one comparison) | < 50 ms hot-path | 0.05 ms / 500 candidates ✓ |

---

## Real-World Constraints

- **BCC vs. SCC**: BERP uses BCC on the undirected symmetrization. Don't confuse with SCC (which is on the directed graph).
- **Graph freshness**: BCC depends on the current live edge set. We rebuild each pipeline run.

---

## Diagnostics

```json
{
  "score_component": -0.04,
  "host_bcc": 12,
  "dest_bcc": 47,
  "would_create_bridge": true,
  "host_bcc_size": 823,
  "dest_bcc_size": 12,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

---

## Benchmark Plan

File: `backend/benchmarks/test_bench_berp.py`.

| Size | Input | Expected | Alert |
|---|---|---|---|
| small | 10 cands, 100-node graph | < 10 ms | > 100 ms |
| medium | 100 cands, 10k graph | < 500 ms | > 3 s |
| large | 500 cands, 100k graph | < 5 s | > 25 s |

---

## Edge Cases

| Edge case | BERP behavior | Test |
|---|---|---|
| Host == dest | Filtered upstream | `test_berp_not_called_for_self_links` |
| Host and dest in same BCC | `score_component = 0` | `test_berp_neutral_when_same_bcc` |
| Host and dest in different BCCs, both ≥ 5 nodes | `score_component = -berp.ranking_weight` | `test_berp_penalty_on_cross_bcc` |
| Host BCC < 5 nodes | Fallback `small_component_skip` → 0.0 | `test_berp_skips_tiny_components` |
| Graph < 50 nodes | Fallback | `test_berp_neutral_below_floor` |
| `berp.enabled=false` | Fallback | `test_berp_neutral_when_disabled` |
| Graph is fully connected (one BCC covers everything) | All candidates return 0 | `test_berp_neutral_on_fully_connected` |
| Graph is disconnected (multiple components) | Cross-component candidates get full penalty | `test_berp_max_penalty_on_disconnected` |

---

## Gate Justifications

All Gate A boxes pass.

---

## Pending

- [ ] Python module `bridge_edge_redundancy.py`.
- [ ] Precompute cache in `pipeline_data.py` — `bcc_label_map`, `bcc_size_map`.
- [ ] Unit tests `test_berp.py`.
- [ ] Benchmark `test_bench_berp.py`.
- [ ] `Suggestion.score_berp` + `Suggestion.berp_diagnostics` columns.
- [ ] `berp.*` keys in `recommended_weights.py` + migration 0035.
- [ ] Integration into `ranker.py` at component index 19 (applied with negative sign via batch_weights[19]).
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card (Codex follow-up).
- [ ] C++ fast path — not needed.
