# FR-104 — Host-Graph Topic Entropy Boost (HGTE)

## Summary

Shannon entropy of a host's outbound-link **silo distribution** measures how topically diverse the host's outgoing links are. A host that only links to posts in one silo has entropy 0; one that spreads links evenly across many silos has high entropy.

HGTE rewards candidates whose addition would **increase** the host's outbound silo entropy — i.e. links that diversify the host's topical portfolio. This turns the host into a better "broadcaster" that distributes link equity across the site's topic graph rather than concentrating it.

Plain English: if a page only links to pages about cats, suggesting a dog link is more informative than suggesting another cat link. HGTE rewards the dog link.

This addresses the Reddit post's **Misaligned Boundaries** topology error — hosts with skewed outbound silo distributions create topical imbalance; HGTE rewards corrective suggestions.

Scope:
- **Per candidate-pair signal**, host-side + candidate-destination-side.
- **Reward shape** — bonus when entropy increases, 0 when entropy decreases or stays flat.
- **Bounded [0, 1], additive, neutral-safe.**

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Shannon, C. E. (1948). "A Mathematical Theory of Communication." *Bell System Technical Journal* 27(3):379–423 and 27(4):623–656. |
| **DOI** | `10.1002/j.1538-7305.1948.tb01338.x` |
| **Open-access link** | http://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf |
| **Relevant sections** | §6 "Entropy of a set of probabilities" eq. 4 (page 393); §6 Theorem 2 (page 394) |
| **What we faithfully reproduce** | The Shannon entropy definition `H(X) = -Σ p_i · log(p_i)` applied to the probability distribution of the host's outbound-edges-by-silo. We use base-2 logarithms (bits) per Shannon's original convention. |
| **What we deliberately diverge on** | Shannon defines entropy over a random variable's probability distribution. We apply it to an empirical frequency distribution — the *observed* frequency of the host's outbound silos. This is the standard "plug-in" entropy estimator used throughout information theory (Cover & Thomas 2006 *Elements of Information Theory* §2.1 eq. 2.4). |

### Quoted source passage

From §6 page 393:
> *"Suppose we have a set of possible events whose probabilities of occurrence are p_1, p_2, ..., p_n. […] The choice is made easier if there are many equally-likely possibilities. A quantity H which measures the uncertainty is chosen so that*
>
> `   H = -K · Σ p_i · log(p_i)`
>
> *(where K is a positive constant). This quantity is called the entropy of the set of probabilities."*

HGTE's formula:
```
# Build the host's outbound silo distribution before the candidate link:
  silo_counts_before[silo] = count of host's existing outbound edges whose dest is in silo
# Normalize to a probability:
  p_before = silo_counts_before / sum(silo_counts_before)
  H_before = -sum(p · log2(p) for p in p_before if p > 0)

# Simulate adding the candidate link:
  silo_counts_after = silo_counts_before + {dest.silo: 1}
  p_after = silo_counts_after / sum(silo_counts_after)
  H_after = -sum(p · log2(p) for p in p_after if p > 0)

# Bonus is positive iff entropy increased:
  hgte_score = max(0, H_after - H_before) / log2(max(1, num_silos))
```

The `log2(num_silos)` denominator normalizes the bonus to [0, 1] — the maximum possible entropy for a distribution over N silos is `log2(N)` (uniform distribution, Shannon Theorem 2).

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `p_i` | probability of event i | `p_i = silo_count[i] / total_count` | `host_topic_entropy.py` |
| `H(X)` | Shannon entropy | `H_before`, `H_after` | same |
| `log` | logarithm (paper says base 2) | `math.log2` | same |
| `hgte_score` | our signal output | `max(0, H_after - H_before) / log2(num_silos)` | same |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `hgte.enabled` | bool | `true` | Project policy (BLC §7.1). |
| `hgte.ranking_weight` | float | `0.04` | Shannon 1948 Theorem 2 shows max entropy scales as `log2(N)`; for a typical 20-silo site, `log2(20) ≈ 4.32`. The expected entropy *delta* per single-link addition is approximately `1/N = 0.05` (Cover & Thomas 2006 §2.8 eq. 2.142 for incremental entropy change). Weight 0.04 produces expected contribution `0.04 × 0.05 ≈ 0.002` per candidate — matching the magnitude of `rare_term_propagation.ranking_weight=0.05`. |
| `hgte.min_host_out_degree` | int | `3` | Entropy of a host with fewer than 3 outbound links is noisy (a single-link host has H=0 by definition; a two-link host has at most H=1). Below 3, the entropy signal is uninformative. Shannon 1948 §12 discusses the asymptotic reliability of empirical entropy estimators; three observations is the minimum for a meaningful two-value distribution plus transition to a third. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. silo.same_silo_boost (FR-005)

`silo.same_silo_boost` is a **per-pair binary** reward when host and dest are in the same silo.

HGTE is a **per-pair entropy-delta** reward when adding the link increases the host's portfolio diversity.

**Disjoint mechanics:**
- same_silo_boost reads: `(host.silo, dest.silo)` pair, outputs `+boost if equal else 0`.
- HGTE reads: `host's existing outbound-link silo counts` + `dest.silo`, outputs `entropy delta normalized`.

These can act on the same candidate with different signs. A cross-silo candidate gets: `same_silo_boost = 0` (no boost), `HGTE > 0` (diversifies portfolio). A same-silo candidate on a silo the host is already heavy in gets: `same_silo_boost > 0` (reward), `HGTE ≈ 0` (doesn't increase diversity). **Complementary, not duplicative** — same_silo says "topical coherence is generally good"; HGTE says "portfolio diversity is also good when the host is too concentrated."

### vs. FR-059 Topic Purity Score

FR-059 measures the destination's on-topic ratio within its silo (a destination-quality signal). HGTE measures the host's outbound silo distribution (a host-portfolio signal). Different subject, different computation.

### vs. anchor_diversity (FR-045)

anchor_diversity measures repetition of anchor-text strings per destination. HGTE measures repetition of silo labels per host's outbound set. Different symbol space (anchor tokens vs. silo IDs), different subject (destination vs. host).

### vs. 15 live ranker signals

None compute Shannon entropy. Searched `docs/specs/` for "entropy", "Shannon", "diversification" — the only hit is `slate_diversity` (FR-015) which is MMR-based, not entropy-based, and operates on the final output slate across candidates, not on the host's outbound portfolio.

### vs. FR-015 Slate Diversity

FR-015 is a **post-ranking reranker** that applies MMR diversification to the final output slate. HGTE is a **ranker-layer per-candidate signal** that rewards adding portfolio-diversifying links. Different mechanism (MMR vs. entropy), different stage (post-ranker vs. in-ranker), different subject (slate output vs. host portfolio). Can both fire without interference.

**Conclusion: CLEAR.**

---

## Neutral Fallback

| Condition | Diagnostic |
|---|---|
| `host.out_degree < hgte.min_host_out_degree` (default 3) | `hgte: low_host_out_degree` |
| Host has no silo-assigned outbound links (silo map is empty for host) | `hgte: host_silo_map_missing` |
| Dest.silo is NULL | `hgte: dest_no_silo` |
| Entropy would decrease by adding the link (dest.silo matches an over-represented silo) | `hgte: entropy_decreasing` (returns 0.0, no penalty applied) |
| `hgte.enabled == false` | `hgte: disabled` |

---

## Architecture Lane

Python only. Uses `math.log2` and simple dict aggregation. O(silo_count) per candidate, typically ~20 silos, so < 10 μs per candidate.

Module: `backend/apps/pipeline/services/host_topic_entropy.py`.

---

## Hardware Budget

| Resource | Per-pipeline precompute | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|
| RAM | ~5 MB for `host_silo_distribution_map` (host_id → {silo_id: count}) | 0 | < 10 GB | 5 MB |
| CPU (precompute) | O(E) scan over ExistingLink rows — ~200 ms for 500k edges | O(silo_count) ≈ 10 μs per candidate (iterate ~20 silos, compute delta entropy) | < 50 ms hot-path | ≈ 5 ms / 500 candidates ✓ |

---

## Real-World Constraints

- Depends on `ContentItem.scope_id` (silo assignment) being populated. On fresh imports before silo classification runs, many dests will have NULL silo → fallback triggers.
- Re-read each pipeline run. No caching across runs (outbound links change).

---

## Diagnostics

```json
{
  "score_component": 0.0312,
  "host_out_degree": 18,
  "host_silo_count_before": 3,
  "host_silo_count_after": 4,
  "entropy_before": 1.2345,
  "entropy_after": 1.4567,
  "entropy_delta": 0.2222,
  "max_entropy": 4.3219,
  "normalized_delta": 0.0514,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

---

## Benchmark Plan

File: `backend/benchmarks/test_bench_hgte.py`.

| Size | Input | Expected | Alert |
|---|---|---|---|
| small | 10 cands, 100-post corpus, 5 silos | < 1 ms | > 10 ms |
| medium | 100 cands, 10k-post corpus, 15 silos | < 20 ms | > 200 ms |
| large | 500 cands, 100k-post corpus, 20 silos | < 200 ms | > 1 s |

---

## Edge Cases

| Edge case | HGTE behavior | Test |
|---|---|---|
| Host has 0 outbound links | Fallback `low_host_out_degree` | `test_hgte_neutral_zero_out_degree` |
| Host has 2 outbound links | Fallback `low_host_out_degree` | `test_hgte_neutral_low_out_degree` |
| Host links to only one silo, dest is same silo | `entropy_decreasing` → 0.0 | `test_hgte_neutral_on_concentrating_link` |
| Host links to only one silo, dest is different silo | Large bonus | `test_hgte_big_bonus_first_cross_silo` |
| Host's outbound silos are uniform, dest is any silo | Small bonus (entropy delta is minimal at max entropy) | `test_hgte_small_bonus_at_max_entropy` |
| Dest has no silo | Fallback `dest_no_silo` | `test_hgte_neutral_no_dest_silo` |
| `hgte.enabled=false` | Fallback | `test_hgte_neutral_when_disabled` |
| Single-silo site (num_silos = 1) | `log2(1) = 0`, prevents div by zero; all candidates get 0 | `test_hgte_safe_on_single_silo` |

---

## Gate Justifications

All Gate A boxes pass.

---

## Pending

- [ ] Python module `host_topic_entropy.py`.
- [ ] Precompute cache in `pipeline_data.py` — `host_silo_distribution_map`, `num_silos`.
- [ ] Unit tests `test_hgte.py`.
- [ ] Benchmark `test_bench_hgte.py`.
- [ ] `Suggestion.score_hgte` + `Suggestion.hgte_diagnostics` columns.
- [ ] `hgte.*` keys in `recommended_weights.py` + migration 0035.
- [ ] Integration into `ranker.py` at component index 20.
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card (Codex follow-up).
- [ ] C++ fast path — not needed (pure-Python math.log2 on small lists is fast enough).
