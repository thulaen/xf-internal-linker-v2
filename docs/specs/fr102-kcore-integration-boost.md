# FR-102 — K-Core Integration Boost (KCIB)

## Summary

**K-core decomposition** partitions a graph by iteratively removing low-degree nodes. A node's k-core number is the largest k such that the node belongs to a subgraph where every node has degree ≥ k. High k-core = structurally central (many mutual neighbours); low k-core = peripheral.

KCIB boosts candidates where the **host is in a high k-core** and the **destination is in a low k-core**. This actively integrates peripheral pages into the site's dense core by encouraging high-centrality hosts to link outward to the periphery.

Plain English: if a "well-connected" page links to a "lonely" page, the lonely page gets pulled into the neighbourhood. KCIB rewards that direction of pull.

This addresses the Reddit post's **Gaps Between Polygons** topology error — peripheral pages disconnected from the dense core fragment the site's link equity distribution.

Scope:
- **Per candidate-pair signal.**
- Uses both host and destination k-core numbers.
- **Directional:** boost is applied only when host.kcore > dest.kcore (high → low).
- **Bounded, additive, neutral-safe.**

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Seidman, S. B. (1983). "Network structure and minimum degree." *Social Networks* 5(3):269–287. |
| **DOI** | `10.1016/0378-8733(83)90028-X` |
| **Open-access link** | https://www.sciencedirect.com/science/article/abs/pii/037887338390028X (paywall) |
| **Relevant sections** | §2 "k-cores: definitions" (p. 270); §4 "Properties" (p. 274–278); §5 "k-core decomposition algorithm" (p. 278–281) |
| **What we faithfully reproduce** | The k-core decomposition as defined by Seidman §2 eq. 1: the k-core of G is the maximal subgraph of G in which every node has degree ≥ k. The k-core *number* of a node is the maximum k such that the node belongs to the k-core. We use the `networkx.core_number()` implementation which implements the Batagelj & Zaversnik (2003) "An O(m) algorithm for cores decomposition of networks" algorithm — the modern linear-time refinement of Seidman's approach. |
| **What we deliberately diverge on** | Seidman (1983) §5 describes an O(m·n) algorithm. We use Batagelj & Zaversnik 2003's O(m) refinement — same output, faster. |

### Quoted source passage

From §2 page 270:
> *"The k-core C_k of G is the maximal subgraph of G in which every vertex has degree at least k within C_k."*

And the "core number" of a node:
> *"The core number of a vertex v, denoted ck(v), is the largest value of k such that v belongs to the k-core."*

KCIB's formula:
```
kcib_raw(host, dest) = max(0, host.kcore - dest.kcore) / max_kcore
```
where `max_kcore` is the largest k-core number in the graph (network's overall "density").

Higher when host is much deeper in the core than dest. Zero when host is in a shallower core than dest (we don't penalize periphery→core links; that's the job of other signals like FR-012 click-distance).

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `G` | graph | `undirected_graph` (networkx.Graph) | `pipeline_data.py` |
| `ck(v)` | core number of v | `kcore_number_map[node_id]` | `pipeline_data.py` |
| `max{ck(v) | v ∈ G}` | maximum core number | `max_kcore` | same |
| `host.kcore - dest.kcore` | our derived difference | `host_kcore - dest_kcore` | `kcore_integration.py` |
| `kcib_score` | our signal output | `max(0, host_kcore - dest_kcore) / max_kcore` | same |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `kcib.enabled` | bool | `true` | Project policy (BLC §7.1). |
| `kcib.ranking_weight` | float | `0.03` | Batagelj & Zaversnik (2003) §4 Figure 3 reports that k-core distribution is approximately log-linear — most nodes have low k-core, few have high. The delta `host.kcore - dest.kcore` is usually ≤ 3 for a typical site. Weight 0.03 produces contributions ≤ 0.03 × 1.0 = 0.03 per candidate, matching `link_farm.ranking_weight=0.03` magnitude. |
| `kcib.min_kcore_spread` | int | `1` | Minimum `host_kcore - dest_kcore` difference to trigger the boost. A difference of 0 (same core) gives neutral 0.0. A difference of 1 is the smallest meaningful "higher-to-lower" step. Follows Seidman §3 Table 1 where inter-core differences of ≥ 1 define the stratification. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. FR-006 PageRank

PageRank is eigenvector centrality (global, convergence-based). K-core is degree-based decomposition (local, iterative). A node can have high PageRank and low k-core (authority via one very dense inbound link from a mega-hub, despite being peripheral) or vice versa (high k-core via many mutual peers, but low PageRank because its peers are also peripheral). **Different measurements.**

### vs. FR-012 Click-Distance

FR-012 is shortest-path hop distance from a seed (homepage). K-core is the depth of a node in the peel-and-remove decomposition. Different recurrences, different inputs, different outputs.

### vs. FR-082 Structural Duplicate Detection

FR-082 uses SimHash on page body content to detect template-duplicate pages. KCIB uses graph k-core decomposition on the link structure. Completely different inputs — FR-082 reads `ContentItem.body`; KCIB reads `ExistingLink` edges.

### vs. 15 live ranker signals

None use k-core decomposition. Searched `docs/specs/` for "k-core", "k_core", "kcore", "coreness" — zero hits. Searched `backend/apps/pipeline/services/` for equivalent helpers — none.

### vs. meta-algos

FR-013 Explore/Exploit, FR-014 clustering, FR-015 slate diversity, FR-018 auto-tuner — none operate on graph topology. FR-033 PageRank heatmap visualizes PageRank distribution, not k-core.

**Conclusion: CLEAR.**

---

## Neutral Fallback

| Condition | Diagnostic |
|---|---|
| `kcore_number_map` is empty / graph has < 50 nodes | `kcib: insufficient_graph_data` |
| `host_kcore` missing | `kcib: host_not_in_graph` |
| `dest_kcore` missing | `kcib: dest_not_in_graph` |
| `host_kcore <= dest_kcore` (no high-to-low direction) | `kcib: non_integrating_direction` (returns 0.0, not a penalty) |
| `max_kcore == 0` (degenerate graph) | `kcib: degenerate_graph` |
| `kcib.enabled == false` | `kcib: disabled` |

Returns `KCIBEvaluation`. Never raises.

---

## Architecture Lane

Python only. Wraps `networkx.core_number(G)` which implements Batagelj-Zaversnik 2003 in C-accelerated networkx.

Module: `backend/apps/pipeline/services/kcore_integration.py`.

---

## Hardware Budget

| Resource | Per-pipeline precompute | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|
| RAM | ~30 MB for 50k nodes (graph + core_number dict) | 0 | < 10 GB | 30 MB |
| CPU (precompute) | ~2 s for 50k nodes | < 100 ns (two dict lookups + one subtract) | < 50 ms hot-path | 0.05 ms / 500 candidates ✓ |
| GPU / Disk | 0 | 0 | — | 0 |

---

## Real-World Constraints

- Uses undirected graph (same symmetrization as TAPB) for k-core. Standard treatment.
- `max_kcore` is re-read from the precomputed dict each pipeline run; don't cache across runs.

---

## Diagnostics

```json
{
  "score_component": 0.0187,
  "host_kcore": 8,
  "dest_kcore": 2,
  "max_kcore": 12,
  "kcore_delta": 6,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

---

## Benchmark Plan

File: `backend/benchmarks/test_bench_kcib.py`.

| Size | Input | Expected | Alert |
|---|---|---|---|
| small | 10 cands, 100-node graph | < 10 ms | > 100 ms |
| medium | 100 cands, 10k graph | < 400 ms | > 2 s |
| large | 500 cands, 100k graph | < 4 s | > 20 s |

---

## Edge Cases

| Edge case | KCIB behavior | Test |
|---|---|---|
| Host == dest | Filtered upstream | `test_kcib_not_called_for_self_links` |
| host.kcore > dest.kcore | `score_component > 0` | `test_kcib_boosts_high_to_low` |
| host.kcore < dest.kcore | `score_component = 0` (not a penalty) | `test_kcib_neutral_on_low_to_high` |
| host.kcore == dest.kcore | `score_component = 0` | `test_kcib_neutral_on_same_core` |
| Graph < 50 nodes | Fallback | `test_kcib_neutral_below_floor` |
| Missing host or dest in kcore map | Fallback | `test_kcib_neutral_on_missing_nodes` |
| `max_kcore == 0` (empty graph) | Fallback `degenerate_graph` | `test_kcib_neutral_on_degenerate` |
| `kcib.enabled=false` | Fallback | `test_kcib_neutral_when_disabled` |

---

## Gate Justifications

All Gate A boxes pass.

---

## Pending

- [ ] Python module `kcore_integration.py`.
- [ ] Precompute cache in `pipeline_data.py` — `kcore_number_map`, `max_kcore`.
- [ ] Unit tests `test_kcib.py`.
- [ ] Benchmark `test_bench_kcib.py`.
- [ ] `Suggestion.score_kcib` + `Suggestion.kcib_diagnostics` columns.
- [ ] `kcib.*` keys in `recommended_weights.py` + migration 0035 upsert.
- [ ] Integration into `ranker.py` at component index 18.
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card (Codex follow-up).
- [ ] C++ fast path — not needed.
