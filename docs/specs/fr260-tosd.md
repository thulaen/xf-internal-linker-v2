# FR-260 — Time-as-Operator Spectral Decay (TOSD)

## Summary

TOSD models link relevance not by simple exponential age decay (which over-penalizes older, stable links and gets tricked by sudden short-lived traffic spikes) but by treating time as a spectral operator on the graph Laplacian. It acts as a low-pass filter: high-frequency (erratic, bursty) changes are suppressed, while low-frequency (stable, historically persistent) relevance is preserved and rewarded.

Plain English: Instead of blindly penalizing a link just because it's old, TOSD looks at its stability. If a link has been consistently valuable over a long period, it keeps a high score. If a link suddenly gets a massive burst of attention that quickly dies off, TOSD ignores the spike.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Temporal/Graph Hybrid** — uses both the age of the link and the structural stability of the nodes.
- **Bounded to `[0, 1]`** via spectral scaling.

---

## Academic Source

| Field | Value |
|---|---|
| **Supporting reference (verified)** | David I. Shuman, Sunil K. Narang, Pascal Frossard, Antonio Ortega, Pierre Vandergheynst, *"The Emerging Field of Signal Processing on Graphs: Extending High-Dimensional Data Analysis to Networks and Other Irregular Domains,"* IEEE Signal Processing Magazine, vol. 30, no. 3, pp. 83–98, May 2013. DOI: [10.1109/MSP.2012.2235192](https://doi.org/10.1109/MSP.2012.2235192). |
| **Citation note** | The earlier draft named a paper *"TimeMM: Time-as-Operator Spectral Filtering for Dynamic Multimodal Recommendation" (2026, arXiv)* with no arXiv ID, DOI, or URL. A web search on 2026-06-15 could not find any paper by that title on arXiv or anywhere else, so it is treated as unverifiable and is NOT used as the citation. Instead we cite the verified foundational graph-signal-processing reference above, which defines the spectral graph filtering framework — including the low-pass filter `H(λ) = 1 / (1 + αλ)` (graph Tikhonov / low-pass form) — that TOSD actually implements. |
| **Relevant sections** | Shuman et al. §III "Graph Spectral Filtering" (defining a graph filter as a function `H(λ)` applied to the Laplacian eigenvalues) and §IV (polynomial / Chebyshev approximation of graph filters). |
| **What we faithfully reproduce** | We use the low-pass spectral graph filtering function `H(λ) = 1 / (1 + αλ)`, where `λ` are the eigenvalues of the normalized graph Laplacian and `α` is the filter strength. This is the standard graph Tikhonov low-pass filter: larger `λ` (faster, more erratic variation across the graph) is attenuated more, while `λ = 0` (a perfectly stable, low-frequency component) passes through unchanged at `H(0) = 1.0`. |
| **What we deliberately diverge on** | The foundational reference describes graph spectral filtering on a single static graph. For the hot-path latency budget we approximate the spectral operator using a fast low-order polynomial (Chebyshev) expansion on a static snapshot of the graph, evaluating it directly during ranking via our Rust kernel rather than performing a full eigendecomposition. |

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `L` | Normalized Graph Laplacian | `laplacian_csr` | precomputed in `pipeline_data.py` |
| `α` | Low-pass filter strength | `tosd.filter_strength` | `recommended_weights.py` |
| `s(t)` | Time-filtered score | `evaluate_tosd()` | `advanced_graph_signals` Rust kernel |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `tosd.enabled` | bool | `true` | Project policy — every shipped signal on by default. |
| `tosd.ranking_weight` | float | `0.06` | Positioned slightly higher than standard `link_freshness` (0.05) to allow spectral stability to override naive freshness. |
| `tosd.filter_strength` | float | `0.8` | This is the `α` in `H(λ) = 1 / (1 + αλ)`. A moderate value near `0.8` filters out high-frequency (erratic, bursty) variation while still letting stable, low-frequency relevance through; see the graph Tikhonov low-pass filter framing in Shuman et al. 2013 (DOI [10.1109/MSP.2012.2235192](https://doi.org/10.1109/MSP.2012.2235192)). The exact value will be re-tuned on real data in the TOSD slice. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. FR-007 Link Freshness Authority
FR-007 decays links uniformly based on `first_seen` and `last_seen`. TOSD relies on structural graph stability (Laplacian eigenvalues) combined with time, ignoring uniform decay in favor of spectral frequency. A 5-year-old link that is structurally central and stable will have a near-zero FR-007 score but a very high TOSD score.

---

## Neutral Fallback

TOSD returns `0.0` when:
- `laplacian_csr` is uninitialized (fresh install).
- Host or Dest not in graph.
- `tosd.enabled == false`.
- The spectral input is non-finite (NaN or infinity) — the Rust kernel sanitises it to `0.0` before clamping.

**Important — `0.0` has two different meanings, distinguished by a diagnostics flag.** The score range is `[0, 1]`, so `0.0` is also the lowest possible *real* score. To tell the two cases apart, every TOSD evaluation sets `fallback_triggered` in `tosd_diagnostics`:

- **Missing data (fallback).** When the host or destination is not in the graph, the graph is uninitialized, the signal is off, or the input is non-finite, TOSD returns `0.0` AND sets `fallback_triggered = true`. This `0.0` means "we could not measure this pair", not "this pair is bad".
- **Genuinely evaluated.** When the pair *was* measured, `fallback_triggered = false`. A genuinely-evaluated isolated or perfectly-stable node has eigenvalue `λ = 0`, so `H(0) = 1.0` — the *highest* score, not `0.0`. A genuinely-evaluated, very-high-frequency (erratic) pair approaches `0.0` from above but is still a real, low score with `fallback_triggered = false`.

So a `0.0` with `fallback_triggered = true` is "no data"; a low score with `fallback_triggered = false` is a real measurement.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | Spectral operator approximations on sparse matrices require zero-overhead math tight loops. |
| **Precompute** | `laplacian_csr` | Built once per pipeline run. |
| **Module location** | `rust/extensions/advanced_graph_signals` | High-performance compiled library. |

---

## Hardware Budget
- RAM: ~50 MB for `laplacian_csr` (scales as `O(nnz)`).
- CPU: < 20 μs per candidate evaluation using 1st-order Chebyshev approximation.

---

## Diagnostics
Outputs `tosd_diagnostics` JSON field containing `raw_spectral_score`, `filter_strength`, and `fallback_triggered`.

---

## Benchmark Plan
Criterion benchmarks in `rust/extensions/advanced_graph_signals/benches/signal_benches.rs` ensuring < 20 μs per evaluation.

---

## Edge Cases
- Isolated nodes: eigenvalue `λ = 0`, so `H(0) = 1 / (1 + α·0) = 1.0` (perfectly stable, no high-frequency neighbour variation). This is a genuine evaluation with `fallback_triggered = false`, NOT a fallback.
- Non-finite spectral input (NaN / ±infinity): the Rust kernel maps it to the neutral `0.0` and sets `fallback_triggered = true`.
- Missing time/graph data (host or dest not in graph, uninitialized graph): returns the neutral `0.0` fallback with `fallback_triggered = true`.
- The final score is always clamped to `[0, 1]`.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [ ] Rust kernel implementation.
- [ ] Python dispatcher integration.
- [ ] UI sliders and tooltips.
