# FR-262 — In-Community Popularity Contrast (ICPC)

## Summary

ICPC scores a destination page based on how popular it is *within its specific, local community* relative to its global PageRank. Highly valuable niche pages often get buried because global authority metrics (like HITS and TrustRank) strongly bias towards generic, high-traffic homepages. ICPC surfaces the "hidden gems" that completely dominate their small sub-graph.

Plain English: If you have a specific guide to "PostgreSQL indexing", it might not be as globally popular as your "Home" page. But *within* the database community of your site, that indexing guide is highly referenced. ICPC acts as an equalizer, rewarding pages that are heroes of their own local communities, even if they aren't globally famous.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Structural Topology Metric** — uses Louvain graph communities.
- **Bounded bonus in `[0, 1]`** — this signal can only add. A value of `1.0` means a local hero whose in-links are almost all in-community; a value near `0` means a globally-popular-but-locally-weak page. The math (a ratio of two non-negative logarithms) can never go below `0`, so ICPC never subtracts and never penalizes. Pages it does not favor simply get a small or zero bonus.

---

## Academic Source

This signal rests on two well-established, citable foundations: the community-detection
method that defines "local community" and the popularity-debiasing line of work that
motivates rewarding niche pages over globally-famous ones.

| Field | Value |
|---|---|
| **Foundational citation (community detection)** | Blondel, V. D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008). "Fast unfolding of communities in large networks." *Journal of Statistical Mechanics: Theory and Experiment*, 2008(10), P10008. DOI: [10.1088/1742-5468/2008/10/P10008](https://doi.org/10.1088/1742-5468/2008/10/P10008) (the Louvain method; arXiv preprint [0803.0476](https://arxiv.org/abs/0803.0476)). |
| **Foundational citation (popularity debiasing)** | Abdollahpouri, H., Burke, R., & Mobasher, B. (2017). "Controlling popularity bias in learning-to-rank recommendation." *RecSys '17*, 42–46. DOI: [10.1145/3109859.3109912](https://doi.org/10.1145/3109859.3109912). |
| **Inspiration (adapted from)** | *Towards Reliable Negative Sampling for Recommendation with Implicit Feedback via In-Community Popularity* (2026). arXiv: [2602.18759](https://arxiv.org/abs/2602.18759). Used as the inspiration for the in-community-popularity idea only; the recent preprint is not relied on as the proof for any default value. The defaults are anchored to the two foundational citations above. |
| **What we faithfully reproduce** | The contrast ratio `ICPC(v) = ln(1 + d_local(v)) / ln(1 + d_global(v))`, where `d_local` is the destination's in-degree counted only inside its own community and `d_global` is its total in-degree. The logarithm base cancels in the ratio, so the choice of base does not matter. Because `d_local <= d_global` always holds (a page cannot have more in-links inside its community than it has in total), the ratio is always in `[0, 1]`. The implementation guards the division against `d_global = 0` (it floors the denominator at a tiny `1e-9`) and clamps the final output to `[0, 1]`. See `evaluate_advanced_graph_signals_core` in `rust/extensions/advanced_graph_signals/src/lib.rs`. |
| **What we deliberately diverge on** | We use this only for ranking, as a positive bonus for niche authority — not for negative sampling. |

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `d_local(v)` | In-degree within community | `community_indegree[v]` | precomputed in `pipeline_data.py` |
| `d_global(v)` | Total in-degree | `global_indegree[v]` | precomputed in `pipeline_data.py` |
| `ICPC(v)` | Contrast score | `evaluate_advanced_graph_signals_core` (writes `score_icpc`) | `advanced_graph_signals` Rust kernel |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `icpc.enabled` | bool | `true` | Project policy. |
| `icpc.ranking_weight` | float | `0.04` | Sits parallel to HITS (0.04) and PPR (0.04) to balance the global authority signals with local authority signals. |
| `icpc.min_community_size` | int | `10` | Prevents trivial 2-node communities from generating massive artificial scores. This threshold is enforced at **precompute time**, not in the Rust kernel: nodes that land in a community smaller than 10 are given **no local in-degree** (`d_local = 0`) when the arrays are built, so for those pages ICPC falls back to a small, near-neutral value instead of an inflated score. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. Graph Signals (HITS, TrustRank, Personalized PageRank)
Those are global metrics. A page with a high TrustRank is globally trusted. ICPC explicitly measures the *delta* between local and global relevance. The math is mathematically orthogonal.

### vs. Node2Vec
Node2Vec provides an embedding representing neighborhood geometry; it measures the *similarity* between host and dest (via cosine). ICPC measures the *standalone niche authority* of the dest, regardless of the host (though restricted to the dest's community).

---

## Neutral Fallback

ICPC degrades to a small, near-neutral value (driven toward `0.0`) when:
- The community partition cache is uninitialized — the dispatcher skips the signal entirely (`icpc.enabled == false` has the same effect).
- The destination sits in a community smaller than `min_community_size` — handled at precompute time by setting `d_local = 0`, so `ln(1 + 0) = 0` makes the ratio `0.0`.
- The Rust kernel itself only guards the arithmetic: if a precompute cell is corrupt (NaN or infinity) it returns `0.0`, and the denominator is floored at `1e-9` so a `d_global = 0` page cannot divide by zero.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | Fast lookups and floating point divisions on the hot-path. |
| **Precompute** | `community_indegree`, `global_indegree` | Built via standard Louvain community detection (via `networkx` or similar) in the daily W1 job, cached into arrays. |
| **Module location** | `rust/extensions/advanced_graph_signals` | High-performance compiled library. |

---

## Hardware Budget
- RAM: ~400 KB for two integer arrays of size 50k.
- CPU: < 1 μs per candidate (two array lookups + one division).

---

## Diagnostics
Outputs `icpc_diagnostics` JSON field containing `local_degree`, `global_degree`, and `contrast_ratio`.

---

## Benchmark Plan
Criterion benchmarks ensuring < 1 μs per evaluation.

---

## Edge Cases
- Global in-degree = 0: the denominator `ln(1 + 0) = 0` is floored to `1e-9`, the numerator is also `0`, and the result clamps to `0.0` (neutral). No division-by-zero.
- Local in-degree = Global in-degree: the ratio reaches its maximum, `1.0` (a local hero — all in-links are in-community).
- Local in-degree < Global in-degree: the ratio lands strictly between `0` and `1` — a positive bonus, never a penalty.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [ ] W1 batch job to compute Louvain communities and local/global indegrees.
- [ ] Rust kernel implementation.
- [ ] Python dispatcher integration.
