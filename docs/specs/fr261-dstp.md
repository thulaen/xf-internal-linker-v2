# FR-261 — Directed Sequential Transition Probability (DSTP)

## Summary

DSTP models the likelihood of a user transitioning from the host page directly to the candidate destination based on historical sequential user paths. Unlike symmetric co-occurrence metrics (which simply measure if A and B appear in the same session), DSTP strictly honors directionality (A → B).

Plain English: If 100 people read "What is Python?" and then immediately read "Python For Loops", the transition probability is high. But almost nobody reads "Python For Loops" and then goes backwards to "What is Python?". DSTP rewards the logical, forward-moving flow of information.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Asymmetric** (Host → Dest probability != Dest → Host).
- **Bounded to `[0, 1]`** via transition matrix normalization.

---

## Academic Source

| Field | Value |
|---|---|
| **Supporting reference 1 — directed transition probability (verified)** | Guy Shani, David Heckerman, Ronen I. Brafman, *"An MDP-Based Recommender System,"* Journal of Machine Learning Research, vol. 6, pp. 1265–1295, 2005. Stable URL: [https://www.jmlr.org/papers/v6/shani05a.html](https://www.jmlr.org/papers/v6/shani05a.html). Defines a recommender as a Markov model over user sessions whose core quantity is the directed transition probability `P(next = B | current = A)` estimated from observed session paths. |
| **Supporting reference 2 — additive (Laplace / Lidstone) smoothing (verified)** | Stanley F. Chen, Joshua Goodman, *"An Empirical Study of Smoothing Techniques for Language Modeling,"* Proc. 34th Annual Meeting of the ACL, 1996, pp. 310–318. DOI: [10.3115/981863.981904](https://doi.org/10.3115/981863.981904); ACL Anthology: [https://aclanthology.org/P96-1041/](https://aclanthology.org/P96-1041/). Surveys additive smoothing — adding a pseudo-count to the denominator so rare, low-count events are not over-estimated — which is exactly the prior we apply to the transition probability. |
| **Citation note** | The earlier draft named a paper *"An Embarrassingly Simple Graph Heuristic Reveals Shortcut-Solvable Benchmarks for Sequential Recommendation" (May 2026, arXiv)* with no arXiv ID, DOI, or URL. A web search on 2026-06-15 could not find any paper by that title, so it is treated as unverifiable and is NOT used as the citation. Instead we cite the two verified foundational references above: one for the directed transition probability and one for the additive smoothing prior we add on top of it. |
| **Relevant sections** | Shani et al. §3 (Markov chains over session sequences; estimating transition probabilities from observed paths). Chen & Goodman §2.1 (additive / Lidstone smoothing). |
| **What we faithfully reproduce — exact implemented formula** | The implemented signal is the **smoothed** directed transition probability `P(B\|A) = count(A → B) / (count(A → *) + α)`, where `count(A → B)` is the number of observed sessions that go directly from page A to page B, `count(A → *)` is the total number of outbound transitions from A, and `α` (`dstp.smoothing_alpha`, default `5.0`) is the additive pseudo-count. This single fraction *is* both the raw probability and the smoothing — the pseudo-count `α` lives only in the denominator. (Note: this is **not** the older `(count + α) / (out_degree + α)` Lidstone form; there is no `+ α` in the numerator. The numerator is the plain observed count.) |
| **What we deliberately diverge on** | The pure transition probability of Shani et al. is `count(A → B) / count(A → *)`, which over-estimates rare pairs (a single one-off A→B session would read as 100%). We add the additive smoothing of Chen & Goodman by putting the pseudo-count `α` in the denominator, which shrinks low-traffic pairs toward `0.0`. A single A→B session with no other outbound traffic from A scores `1 / (1 + α)` ≈ `0.17` at `α = 5.0`, not `1.0`. |

---

## Mapping: Paper Variables → Code Variables

| Symbol | Meaning | Code identifier | File |
|---|---|---|---|
| `count(A → B)` | Observed A→B transition occurrences (numerator) | `transition_counts_csr` | precomputed in `pipeline_data.py` |
| `count(A → *)` | Total outbound transitions from A (denominator before smoothing) | `transition_out_degrees` | precomputed in `pipeline_data.py` |
| `α` | Additive smoothing pseudo-count added to the denominator | `dstp.smoothing_alpha` | `recommended_weights.py` |
| `P(B\|A) = count(A → B) / (count(A → *) + α)` | Smoothed transition probability | `evaluate_dstp()` | `advanced_graph_signals` Rust kernel |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `dstp.enabled` | bool | `true` | Project policy. |
| `dstp.ranking_weight` | float | `0.08` | High confidence signal; historically, behavioral transitions are the strongest indicators of next-click relevance. |
| `dstp.smoothing_alpha` | float | `5.0` | The additive pseudo-count `α` in the denominator `count(A → *) + α`. With `α = 5.0`, a page needs on the order of 5 outbound transitions before the smoothing stops dominating, so a handful of one-off clicks cannot reach a high score. Additive smoothing is the Lidstone / Laplace family from Chen & Goodman 1996 (DOI [10.3115/981863.981904](https://doi.org/10.3115/981863.981904)). The exact value will be re-tuned on real clickstream data in the DSTP slice. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. FR-025 Session Co-Occurrence Collaborative Filtering
FR-025 uses Jaccard similarity to cluster pages that appear in the same sessions. Jaccard is strictly symmetric (`J(A,B) == J(B,A)`). DSTP is strictly asymmetric, mapping the chronological intent of the reader. It overrides the symmetric clustering with a strict directed chronological vector.

---

## Neutral Fallback

DSTP returns `0.0` when:
- Transition matrices are uninitialized (no session logs available).
- Host has no outbound sequential traffic.
- `dstp.enabled == false`.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | Fast CSR row lookups and Bayesian smoothing math during the hot-path ranking phase. |
| **Precompute** | `transition_counts_csr` | Sourced from `piwik_log_link_visit_action` (or equivalent clickstream logs) daily. |
| **Module location** | `rust/extensions/advanced_graph_signals` | Single unified crate for all advanced graph math. |

---

## Hardware Budget
- RAM: ~10 MB for sparse transition matrices.
- CPU: < 5 μs per candidate (O(1) sparse lookup).

---

## Diagnostics
Outputs `dstp_diagnostics` JSON field containing `raw_probability`, `smoothed_probability`, and `total_host_transitions`.

The ranking uses the **smoothed** value, not the raw one:

- **`raw_probability`** = `count(A → B) / count(A → *)` — the plain transition probability with no smoothing. This is shown for transparency only; it can read a misleading `1.0` for a single one-off session. It is not what feeds the ranker.
- **`smoothed_probability`** = `count(A → B) / (count(A → *) + α)` — the value the ranker actually consumes (computed in the Rust kernel as `evaluate_dstp()`), with `α = dstp.smoothing_alpha`.
- **`total_host_transitions`** = `count(A → *)`, the outbound traffic from the host page. When this is `0` the host is a cold-start node (see Edge Cases).

---

## Benchmark Plan
Criterion benchmarks in `rust/extensions/advanced_graph_signals/benches/signal_benches.rs`.

---

## Edge Cases
- Cold start nodes: a host with no recorded transitions has `count(A → B) = 0` and `count(A → *) = 0`, so the smoothed score is `0 / (0 + α) = 0.0` — the neutral fallback. This is `0.0` (the lowest score), NOT the maximum. The additive `α` in the denominator is what guarantees there is no division by zero and that an unseen pair lands at the neutral `0.0`.
- Non-finite input: the Rust kernel maps NaN / ±infinity to `0.0` before clamping.
- High traffic hubs: smooth correctly because the large `count(A → *)` makes the `+ α` pseudo-count negligible, so the smoothed value converges to the raw probability.
- The final score is always clamped to `[0, 1]`.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [ ] Transition matrix builder from DB logs.
- [ ] Rust kernel implementation.
- [ ] Python dispatcher integration.
