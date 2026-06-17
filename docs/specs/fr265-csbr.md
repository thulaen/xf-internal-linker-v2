# FR-265 — Cross-Silo Bridging Reward (CSBR)

## Summary

CSBR encourages healthy cross-pollination by identifying links that span distinct content silos *if and only if* those pages share a strong thematic "bridging persona" (deep semantic overlap in specific structural zones). It acts as an intelligent counterbalance to the strict penalty usually applied to cross-silo links.

Plain English: Normally, we heavily penalize a link going from the "Baking" category to the "Automotive" category, because it's usually irrelevant spam. But what if the "Baking" page is about "Industrial Oven Maintenance" and the "Automotive" page is about "High-Temperature Paint Curing"? CSBR detects this deep thematic overlap and actively rewards the link for brilliantly bridging two distinct categories.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Semantic/Category Hybrid** — requires silo mismatch AND high persona match (high topic overlap).
- **Bounded to `[0, 1]`** — a perfect cross-silo bridge scores `1.0`; everything that fails the silo test or the overlap test scores `0.0`. See "Implemented Formula" below.

---

## Academic Source

We could not verify the originally-cited title (*Breaking the Information Silo: Semantic Personas for Cross-Domain Recommendation*, June 2026) as a real, stably-identified paper, so we do not rely on it. CSBR is built from two well-established, peer-reviewed techniques instead, and we cite both. The first gives us the topics for each page; the second gives us the standard, bounded way to measure how much two topic mixes overlap.

| Field | Value |
|---|---|
| **Citation 1 — topic model** | Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003). *Latent Dirichlet Allocation.* Journal of Machine Learning Research, 3, 993–1022. https://jmlr.org/papers/volume3/blei03a/blei03a.html |
| **Citation 2 — overlap measure** | Lin, J. (1991). *Divergence Measures Based on the Shannon Entropy.* IEEE Transactions on Information Theory, 37(1), 145–151. DOI: 10.1109/18.61115 |
| **Why these references** | Latent Dirichlet Allocation (LDA) turns each page into a list of topic weights that add up to 1 (a probability distribution). The Jensen–Shannon divergence (defined in Lin 1991) is the standard, symmetric, always-bounded way to score how different two such distributions are; with log base 2 it sits in `[0, 1]`. CSBR turns that "how different" number into a "how similar" number and rewards strong topic overlap across silos. |
| **What we faithfully reproduce** | The bridging reward shape `R = indicator(Silo_host != Silo_dest) * ReLU(PersonaMatch - Threshold)`, and the Jensen–Shannon divergence exactly as Lin (1991) defines it. |
| **What we deliberately diverge on** | We do not generate the rich, LLM-written "personas" the original idea imagined. We reuse the LDA topic distributions we already compute and define `PersonaMatch = 1 - JensenShannonDivergence(topics_host, topics_dest)`, keeping the whole thing fast on the hot path. |

---

## Mapping: Concept → Code Variables

| Concept | Meaning | Code identifier | File |
|---|---|---|---|
| `Domain(i)` | Content silo | `dest_silo_id`, `host_silo_id` | existing variables |
| `is_cross_silo` | 1 if host and dest are in different silos, else 0 | `is_cross_silo` | precomputed Python-side, passed to the kernel |
| `PersonaMatch` | Topic **similarity** in `[0, 1]`, where higher = more overlap. Computed as `1 - JensenShannonDivergence(LDA topics)` on the Python side before it reaches the kernel. | `persona_matches` | precomputed Python-side, passed to the kernel |
| `Threshold` | Minimum **similarity** required to start rewarding (on the same `[0, 1]` similarity scale) | `csbr.min_overlap_threshold` | `recommended_weights.py` |
| `R(i, j)` | Bridging reward | `evaluate_advanced_graph_signals_core()` (CSBR branch) | `rust/extensions/advanced_graph_signals/src/lib.rs` |

---

## Implemented Formula

This is exactly what the Rust kernel computes (`rust/extensions/advanced_graph_signals/src/lib.rs`, CSBR branch), written here in plain steps.

1. **Turn "how different" into "how similar".** On the Python side, each page already has an LDA topic distribution (a list of topic weights that adds up to 1). We measure how *different* the host's and dest's topic mixes are with the Jensen–Shannon divergence using log base 2, which always lands in `[0, 1]` (`0` = identical topics, `1` = completely different). We then flip it into a *similarity*:

   `PersonaMatch = 1 - JensenShannonDivergence(LDA_topics(host), LDA_topics(dest))`

   So `PersonaMatch` is in `[0, 1]` and **higher means more topic overlap**. This is the line that resolves the old contradiction: the formula talks about `PersonaMatch` (higher = more similar), and the actual measure under the hood is Jensen–Shannon divergence (higher = more different). The `1 - ...` conversion bridges the two so the reward below correctly fires on **high** overlap.

2. **Gate on a real cross-silo jump.** If host and dest are in the **same** silo, the reward is `0.0` — there is nothing to bridge. The reward only turns on when `is_cross_silo` is true (host silo ≠ dest silo).

3. **Reward overlap above the threshold (a ReLU):**

   `raw = max(PersonaMatch - Threshold, 0)`

   where `Threshold` is `csbr.min_overlap_threshold` (default `0.7`, measured on the same `[0, 1]` similarity scale). If the topic overlap is at or below `0.7`, the raw reward is `0.0`; above `0.7`, it grows. `max(..., 0)` is the ReLU ("rectified linear unit" — anything negative becomes zero).

4. **Rescale so a perfect bridge reaches `1.0`:**

   `R = clamp( raw / (1 - Threshold), 0, 1 )`

   Dividing by `(1 - Threshold)` stretches the usable band (`0.7`→`1.0` of overlap) back up to a full `0.0`→`1.0` reward. With the default threshold, a perfect overlap (`PersonaMatch = 1.0`) gives `(1.0 - 0.7) / (1 - 0.7) = 1.0`. That full `1.0` is deliberate: it lets a flawless cross-silo bridge exactly cancel the separate cross-silo penalty.

**Putting it together:**

`R = clamp( indicator(Silo_host != Silo_dest) * max(PersonaMatch - Threshold, 0) / (1 - Threshold), 0, 1 )`

**Neutral / missing-data behaviour:** same silo → `0.0`; missing LDA vector (so no `PersonaMatch`) → `0.0`; overlap at or below the threshold → `0.0`. In every neutral case the reward is a clean zero, matching the "Neutral Fallback" rule below.

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `csbr.enabled` | bool | `true` | Project policy. |
| `csbr.ranking_weight` | float | `0.05` | Matches the magnitude of the existing `silo.cross_silo_penalty` (0.05), allowing a perfect bridging link to exactly cancel out the silo penalty. |
| `csbr.min_overlap_threshold` | float | `0.7` | Measured on the topic-**similarity** scale (`PersonaMatch = 1 - Jensen–Shannon divergence`, so `1.0` = identical topics). A high `0.7` cut-off means we only reward genuinely strong bridging overlap, not random coincidences. Jensen–Shannon divergence is the bounded, symmetric overlap measure from Lin (1991), DOI 10.1109/18.61115. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. `silo.cross_silo_penalty`
`silo.cross_silo_penalty` is a blunt instrument: if Silo A != Silo B, apply a penalty. CSBR is the surgical counter-measure: if Silo A != Silo B AND the topic overlap is massive, apply a reward.

### vs. LDA (Pick #18)
The standard LDA signal evaluates general topic similarity globally. CSBR is a conditional gate: the score is *strictly zero* if the pages are in the same silo. It explicitly identifies and rewards structural bridging.

---

## Neutral Fallback

CSBR returns `0.0` when:
- Host and Dest are in the same silo.
- Host or Dest lacks an LDA vector.
- `csbr.enabled == false`.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language** | Rust via PyO3 | The hot-path reward maths (the cross-silo gate, the ReLU above the threshold, the rescale, and the clamp) runs per candidate for thousands of candidates and benefits from compiled, allocation-free code. |
| **Precompute** | `lda_topic_vectors` → `persona_matches` | LDA topic vectors are already generated by the W1 LDA job. The `PersonaMatch = 1 - Jensen–Shannon divergence` conversion is done Python-side, so the Rust kernel receives the ready-made `persona_matches` similarity array (in `[0, 1]`) rather than recomputing the divergence. |
| **Module location** | `rust/extensions/advanced_graph_signals` | High-performance compiled library. |

---

## Hardware Budget
- RAM: ~0 MB (reuses existing LDA arrays).
- CPU: < 1 μs per candidate.

---

## Diagnostics
Outputs `csbr_diagnostics` JSON field containing `is_cross_silo`, `persona_match`, and `score`.

---

## Benchmark Plan
Criterion benchmarks ensuring < 1 μs per evaluation.

---

## Edge Cases
- Missing silo assignments: Fails safe to 0.0.
- Exactly matching silos: Fails safe to 0.0.

---

## Gate Justifications
All Gate A boxes pass.

---

## Pending
- [x] Python-side `PersonaMatch = 1 - Jensen–Shannon divergence` precompute that feeds the kernel's `persona_matches` array.
- [x] Python dispatcher integration.
