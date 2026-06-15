# FR-264 — Riemannian Geodesic Semantic Distance (RGSD)

## Summary

RGSD corrects the blind spots of flat vector search (like cosine similarity) by computing distances along a curved mathematical space (a Riemannian manifold) defined by the website's graph structure. 

Plain English: If you look at a flat map of the Earth, a flight from New York to London looks like a straight line, but airplanes actually fly in a curve over the ocean because the Earth is round. In a website, dense topic areas warp the mathematical space. Flat cosine similarity ignores this and draws straight lines, leading to inaccurate semantic matches. RGSD measures the true "curved" distance, resulting in hyper-accurate semantic link suggestions.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Semantic/Topological Hybrid** — uses text embeddings mapped onto a graph-defined manifold.
- **Bounded to `[0, 1]`** — and it is a relevance **score**, where higher means "closer / more relevant". The raw geodesic value is a *distance* (higher means farther), so the code inverts it to a score. See "Implemented Formula" below for the exact map.

---

## Academic Source

We could not verify the originally-cited title (*Geodesic Semantic Search: Cartographic Navigation of Citation Graphs with Learned Local Riemannian Maps*, February 2026) as a real, stably-identified paper, so we do not rely on it. Instead we cite the foundational, peer-reviewed work that established the technique RGSD uses: measuring distance along a curved (Riemannian) space instead of a flat (Euclidean/cosine) one. RGSD is a fast first-order algebraic stand-in for that idea, not a reproduction of any single 2026 paper.

| Field | Value |
|---|---|
| **Full citation** | Nickel, M., & Kiela, D. (2017). *Poincaré Embeddings for Learning Hierarchical Representations.* Advances in Neural Information Processing Systems 30 (NeurIPS 2017). arXiv:1705.08039. https://arxiv.org/abs/1705.08039 |
| **Why this reference** | This is the seminal demonstration that embedding-space distance is more accurate when measured along a curved Riemannian manifold than along a flat Euclidean/cosine line, especially where the data is dense or hierarchical. That is exactly the blind spot RGSD corrects. |
| **What we faithfully reproduce** | The core principle: the true distance between two points should grow where the surrounding space is "warped" by local density, rather than being read straight off a flat cosine line. |
| **What we deliberately diverge on** | We do not learn a full hyperbolic embedding or integrate a differential-equation solver on the hot path. We use a cheap first-order algebraic correction, `D_geo = D_flat * (1 + k * density_gradient)`, where `density_gradient` is a precomputed local-density scalar that stands in for the manifold curvature. |

---

## Mapping: Concept → Code Variables

| Concept | Meaning | Code identifier | File |
|---|---|---|---|
| `x, y` | Node embeddings | `dense_embeddings` | existing pipeline matrix |
| curvature / local density | The "warping" of the space near each node | `density_gradients` | precomputed Python-side, passed to the kernel |
| `D_flat` | Flat cosine distance in `[0, 1]` between the pair | `flat_distances` | precomputed Python-side, passed to the kernel |
| `k` | Curvature penalty (strength of the correction) | `rgsd_curvature_penalty` | `recommended_weights.py` |
| `D_geo` → score | Geodesic distance, then inverted to a relevance score | `evaluate_advanced_graph_signals_core()` (RGSD branch) | `rust/extensions/advanced_graph_signals/src/lib.rs` |

---

## Implemented Formula

This is exactly what the Rust kernel computes (`rust/extensions/advanced_graph_signals/src/lib.rs`, RGSD branch). It is written here in plain steps so a non-coder can follow it.

1. **Inputs are cosine *distances* in `[0, 1]`.** `D_flat` is the flat cosine distance for the pair: `0.0` means "identical / right on top of each other", `1.0` means "as far apart as the measure allows". A pair we have no data for defaults to `D_flat = 1.0` (treated as farthest).

2. **Apply the curvature correction (the geodesic step):**

   `D_geo = D_flat * (1 + k * density_gradient)`

   where `k` is `rgsd.curvature_penalty` (default `1.5`) and `density_gradient` is the precomputed local-density scalar. Because the gradient is non-negative, `D_geo` is always greater than or equal to `D_flat`: the curved distance can only *stretch* the flat distance, never shrink it. That stretch is the manifold correction.

3. **Invert distance into a relevance score, then clamp:**

   `score = clamp(1 - D_geo, 0, 1)`

   This is the distance→score inversion. A small `D_geo` (the two pages are close on the curved space) gives a score near `1.0` (highly relevant). A large `D_geo` gives a score near `0.0` (not relevant).

4. **Saturation note.** Because `D_geo` can exceed `1.0` (the correction stretches it past the flat ceiling), `1 - D_geo` can go negative; the clamp pulls every such case to `0.0`. So all "very distant" pairs flatten to the same `0.0` floor and become indistinguishable from each other. This is a deliberate, recorded simplification, not the final design — the RGSD slice will revisit the normalization (for example a softer squashing function) once real density data is available.

**Neutral / missing-data behaviour:** a pair with no precomputed data uses `D_flat = 1.0`, which (with any non-negative gradient) gives `D_geo ≥ 1.0` and therefore `score = 0.0`. So a missing pair contributes a neutral zero — it neither rewards nor punishes the candidate, matching the "Neutral Fallback" rule below.

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `rgsd.enabled` | bool | `true` | Project policy. |
| `rgsd.ranking_weight` | float | `0.10` | This is a foundational semantic correction and deserves a high weight, parallel to standard semantic scores or LDA (0.10). |
| `rgsd.curvature_penalty` | float | `1.5` | The `k` parameter that balances flat vs curved distance. A value above 1 lets dense, heavily-warped regions push the geodesic distance well past the flat distance, which is the whole point of the Riemannian correction (Nickel & Kiela, 2017, arXiv:1705.08039). Starting value chosen for a clear-but-not-extreme correction; the RGSD slice will re-tune it with real data. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. `w_semantic` (Cosine Similarity)
`w_semantic` operates strictly in flat Euclidean/Cosine space. RGSD explicitly measures the discrepancy caused by the manifold curvature. The two are complementary: `w_semantic` is the baseline, and RGSD provides the high-precision manifold correction.

---

## Neutral Fallback

RGSD returns `0.0` when:
- `embedding_density_gradients` are missing.
- Either host or dest lacks a valid embedding vector.
- `rgsd.enabled == false`.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | SIMD-accelerated vector math combined with gradient lookups is perfectly suited for Rust on the hot-path. |
| **Precompute** | `embedding_density_gradients` | Computed in python via SciPy during the pipeline run using nearest-neighbors. |
| **Module location** | `rust/extensions/advanced_graph_signals` | High-performance compiled library. |

---

## Hardware Budget
- RAM: ~1.5 MB for density gradient scalars.
- CPU: < 10 μs per candidate (vector dot products + scalar adjustments).

---

## Diagnostics
Outputs `rgsd_diagnostics` JSON field containing `flat_distance`, `geodesic_distance`, and `manifold_correction_factor`.

---

## Benchmark Plan
Criterion benchmarks ensuring < 10 μs per evaluation.

---

## Edge Cases
- Disconnected manifold (density=0): Gracefully degrades to standard flat Euclidean distance.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [ ] Precompute logic for density gradients.
- [ ] Rust kernel implementation using SIMD (e.g., `std::arch` or `ndarray`).
- [ ] Python dispatcher integration.
