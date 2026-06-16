# FR-263 — Stochastic Block Model Affinity (SBMA)

## Summary

SBMA models link probability based on the structural roles (blocks) of the host and destination pages. A Stochastic Block Model partitions a graph into groups where nodes within a group connect to other groups with the same probability. It identifies macro-patterns like "Core Hubs", "Periphery Nodes", or "Bridge Pages", and scores candidate links based on how often these roles historically link to each other.

Plain English: If you have a cluster of pages that act as "Table of Contents" directories, they naturally link outwards to "Detail" pages, but "Detail" pages rarely link to each other. SBMA learns these roles. It boosts links that follow the natural architectural rules of the site, even if the two pages are in entirely different topic areas.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Structural Role Metric** — independent of semantic content or specific neighborhoods.
- **Bounded to `[0, 1]`** (a strict probability). The Rust kernel does **one O(1) pass-through**: the inter-block probability `BlockMatrix[Block(host), Block(dest)]` is looked up Python-side first, then the kernel simply clamps that single value to the `[0, 1]` probability range. See `evaluate_advanced_graph_signals_core` (writes `score_sbma`) in `rust/extensions/advanced_graph_signals/src/lib.rs`.

---

## Academic Source

This signal rests on the well-established stochastic block model (SBM) literature: a graph's
nodes are sorted into blocks (roles), and the chance of a link between two nodes depends only
on which blocks they belong to.

| Field | Value |
|---|---|
| **Foundational citation (SBM, origin)** | Holland, P. W., Laskey, K. B., & Leinhardt, S. (1983). "Stochastic blockmodels: First steps." *Social Networks*, 5(2), 109–137. DOI: [10.1016/0378-8733(83)90021-7](https://doi.org/10.1016/0378-8733(83)90021-7). |
| **Foundational citation (degree-corrected SBM)** | Karrer, B., & Newman, M. E. J. (2011). "Stochastic blockmodels and community structure in networks." *Physical Review E*, 83(1), 016107. DOI: [10.1103/PhysRevE.83.016107](https://doi.org/10.1103/PhysRevE.83.016107) (arXiv preprint [1008.3926](https://arxiv.org/abs/1008.3926)). |
| **Inspiration (adapted from)** | *TGSBM: Transformer-Guided Stochastic Block Model for Link Prediction* (2026). arXiv: [2601.20646](https://arxiv.org/abs/2601.20646). Used only as inspiration for treating the block-to-block matrix as a link-affinity lookup; this recent preprint is not relied on as the proof for any default value. The defaults are anchored to the two foundational citations above. |
| **What we faithfully reproduce** | The probability lookup `P(A → B) = BlockMatrix[Block(A), Block(B)]`. The block assignments and the inter-block probability matrix are computed offline; the host and destination are mapped to their blocks **before** the kernel runs, so the kernel sees a single already-resolved probability per candidate. |
| **What we deliberately diverge on** | We skip the transformer-guided block generation. The first production implementation reuses the already-computed graph communities as bounded structural blocks, then stores the observed block-to-block link probability matrix for request-time lookup. This keeps the daily job deterministic, testable, and fast while preserving the SBM scoring shape: page block plus destination block selects one learned probability. |

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `z_i` | Block assignment of node i | `NodeGraphSignal.sbma_block_id` | stored by `graph_signal_job.py`, loaded by `pipeline_data.py` |
| `B_rs` | Probability of edge between block r and block s | `GraphSignalRun.sbma_matrix_json` / `block_transition_matrix` | stored by `graph_signal_job.py`, loaded by `pipeline_data.py` |
| `P(i, j)` | Link affinity | `evaluate_advanced_graph_signals_core` (writes `score_sbma`) | `advanced_graph_signals` Rust kernel |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `sbma.enabled` | bool | `true` | Project policy. |
| `sbma.ranking_weight` | float | `0.05` | Matches standard topological signals like Node2Vec (0.05). |
| `sbma.num_blocks` | int | `20` | Sufficient resolution for macro-structural roles without over-fitting to specific neighborhoods. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. Node2Vec (Pick #37)
Node2Vec captures *community/neighborhood proximity*. Two nodes close together in the graph have a high Node2Vec similarity. SBMA captures *structural equivalence*. A Hub page in "Biology" and a Hub page in "Physics" might be far apart in the graph (low Node2Vec), but they belong to the same SBM Block (Hubs). If the site architecture naturally points Hubs to Details, SBMA rewards it regardless of topic.

---

## Neutral Fallback

SBMA returns the neutral value `0.0` when:
- `node_block_assignments` or `block_transition_matrix` are missing.
- Host or Dest is not in the block mapping (one or both pages were never assigned a block).
- `sbma.enabled == false`.

**Important distinction.** A `0.0` from a *missing mapping* (a page that has no block at all) is **not the same** as a `0.0` from a *genuine* inter-block probability of zero (two real blocks that the offline model learned never link to each other). The first is a fallback — we have no information; the second is a real, learned "these roles do not link" answer. To keep them apart, the missing-mapping case is recorded in diagnostics under `fallback_triggered = true`. A genuine learned zero leaves `fallback_triggered = false`. Both produce the same `0.0` score, but only the fallback case is flagged.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | O(1) array lookups; keeping it in the unified advanced graph crate. |
| **Precompute** | `sbma_block_id` and `sbma_matrix_json` | The daily graph-signals job stores bounded page blocks and the block-to-block probability table; request-time ranking only loads arrays and performs an O(1) lookup. |
| **Module location** | `rust/extensions/advanced_graph_signals` | High-performance compiled library. |

---

## Hardware Budget
- RAM: ~200 KB for an integer array of size 50k (node->block map) + trivial 20x20 float matrix.
- CPU: < 1 μs per candidate (two array lookups).
- Dell proof, 2026-06-16: offline block precompute benchmarked at 167 us for 100 nodes, 1.31 ms for 1,000 nodes, and 12.48 ms for 10,000 nodes.

---

## Diagnostics
Outputs `sbma_diagnostics` JSON field containing `host_block`, `dest_block`, `block_affinity_probability`, and `fallback_triggered`. The `fallback_triggered` flag is `true` only when the host or destination had no block mapping (the neutral fallback fired), and `false` when the `0.0` is a genuinely-learned zero inter-block probability.

---

## Benchmark Plan
Pytest benchmark coverage proves the daily precompute path at 100, 1,000, and 10,000 nodes. The Rust kernel benchmark remains the proof for per-candidate O(1) evaluation, because the kernel only clamps the already-resolved probability.

---

## Edge Cases
- Block transition probability is a genuine `0.0` (two real blocks that never link): outputs `0.0` (minimum score) with `fallback_triggered = false`.
- Host or destination has no block mapping: outputs the neutral `0.0` with `fallback_triggered = true` — distinct from the genuine-zero case above.
- Corrupt precompute cell (NaN or infinity): the kernel sanitises it to `0.0` before clamping, so a bad cell degrades to neutral instead of poisoning the score.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [x] W1 batch job computes and stores page block assignments plus the transition matrix through the daily graph-signals job.
- [x] Rust kernel implementation.
- [x] Python dispatcher integration.
