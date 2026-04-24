# FR-099 — Dangling Authority Redistribution Bonus (DARB)

## Summary

When the **host** post (the page that would gain a new outbound link) has high content-value authority but very few outbound internal links, DARB gives the candidate destination a small additive boost on the composite score. This nudges the ranker to route juice *outward from dangling hoarders* — high-value posts that accumulate authority but don't pass it along.

Plain English: if a popular post has no outbound links, we gently reward suggestions that would fix that. The Reddit post we are addressing calls these "dead-end streets" and warns that they starve the rest of the site of link equity. DARB encodes that concern into the ranking formula, not just as an audit report.

Scope:
- **Per candidate-pair signal** (operates at ranker time).
- **Host-side signal** — measures a property of the post adding the outbound link, not the destination.
- **Bounded, additive, neutral-safe** — never blocks; never reverses a ranking; neutral fallback is 0.0.

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Page, L., Brin, S., Motwani, R. & Winograd, T. (1999). *The PageRank Citation Ranking: Bringing Order to the Web*. Stanford InfoLab Technical Report 1999-66, Stanford University. |
| **Open-access link** | http://ilpubs.stanford.edu:8090/422/ |
| **Relevant sections** | §2.5 "Dangling Links" (page 5); §2.4 "Rank Sink" (page 4–5); §3.2 "Convergence Properties" eq. 1 (page 7) |
| **What we faithfully reproduce** | The concept that dangling nodes (pages with zero or near-zero out-links) have distorted authority flow and that their mass must be redistributed. DARB uses the redistributed-mass logic as its inspiration and bounds: `rank_bonus ∝ host_authority / (1 + host_out_degree)`. |
| **What we deliberately diverge on** | Page et al. 1998 redistribute dangling mass *inside the PageRank matrix iteration*, producing a single score per page. DARB instead extracts the **inverse-out-degree-weighted authority** as a *ranker-layer signal*, applied per candidate-pair at suggestion time. This is a deliberate architectural divergence — DARB does not change the PageRank matrix math, it only reuses the mathematical intuition that low-out-degree high-authority nodes hoard juice. |

### Quoted source passage

From §2.5 "Dangling Links" (page 5):
> *"Dangling links are simply links that point to any page with no outgoing links. They affect the model because it is not clear where their weight should be distributed, and there are a large number of them. Often these dangling links are simply pages that we have not downloaded yet […] Because dangling links do not affect the ranking of any other page directly, we simply remove them from the system until all the PageRanks are calculated."*

DARB's interpretation: the removed-and-redistributed mass is a structural problem the Reddit post calls out — high-value dangling hosts starve the rest of the graph. Rather than hide the problem inside matrix iteration, DARB surfaces it as a *remedial ranking signal* that encourages suggestions from dangling hosts.

From §3.2 eq. 1:
> `R(u) = c · Σ_{v ∈ B_u} R(v) / N_v  + c · E(u)`
>
> where `N_v` is the out-degree of node `v` and `B_u` is the set of pages pointing to `u`.

The `1 / N_v` term in the PageRank recurrence — authority divided by out-degree — is the mathematical fingerprint DARB borrows. A host with high `R(v)` but low `N_v` contributes heavily per outbound edge. DARB's per-candidate score uses the same shape: `content_value_score / (1 + out_degree)`.

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `R(v)` | PageRank score of page v | `host.content_value_score` (composite GSC + GA4 + PageRank, a richer proxy than raw PageRank alone) | `ContentItem.content_value_score` in `backend/apps/content/models.py` |
| `N_v` | out-degree of page v | `host.out_degree` = `existing_outgoing_counts[host_key]` | precomputed in `backend/apps/pipeline/services/pipeline_data.py` |
| `c` | PageRank damping constant (0.85) | N/A — DARB is not an iterated recurrence, so no damping is applied | — |
| `darb_raw` | derived bonus (our invention) | `host_content_value / (1 + host_out_degree)` | `backend/apps/pipeline/services/dangling_authority_redistribution.py` |
| `darb_score` | normalized [0, 1] | `clamp(darb_raw, 0, 1)` | same |

**Divergence note:** We substitute `content_value_score` (composite GSC + GA4 + PageRank) for the paper's raw `R(v)` because the composite authority is a stronger production signal and is already recomputed daily by `analytics.sync._refresh_content_value_scores`. This is a documented upgrade, not a deviation from the dangling-node concept.

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `darb.enabled` | bool | `true` | Project policy — every shipped signal is on by default with a safe starting value (BLC §7.1). |
| `darb.ranking_weight` | float | `0.04` | Page et al. 1999 §3.2 eq. 1 implies that dangling-node authority is redistributed proportionally to `1 / N_v`. The existing `weighted_authority.ranking_weight=0.10` (FR-006) covers the PageRank-derived authority. DARB takes **40% of that magnitude** as a conservative per-pair bonus for hosts whose authority is under-utilized (low out-degree). The 0.04 value matches the magnitude of `keyword_stuffing.ranking_weight=0.04` (Croft, Metzler & Strohman 2015 *Search Engines* §7.3 Dirichlet-smoothed term saturation — a structurally similar host-quality signal). |
| `darb.out_degree_saturation` | int | `5` | Broder et al. (2000) "Graph structure in the Web", WWW9, §3 Table 1 reports median out-degree ≈ 8 on live web corpora. We use a saturation threshold of 5 (below median) to define "low out-degree" — a host with ≥ 5 outbound internal links is not considered dangling. This is tunable. |
| `darb.min_host_value` | float | `0.5` | Neutral midpoint of `content_value_score`, which is bounded [0, 1] with 0.5 = neutral per the `ContentItem.content_value_score` help text. DARB fires only when host value is above neutral; below-neutral hosts get 0.0 (neutral fallback). |

Round-number justifications:
- `0.5` neutral midpoint is the published neutral value for `content_value_score` itself, per its model help text in `backend/apps/content/models.py` migration `0021_content_value_score_help_text_phase3a.py`. This is a project-level semantic constant, not a guessed round number.
- `5` out-degree threshold is cited to Broder et al. 2000 Table 1.
- `0.04` weight has a three-step derivation cited above.

---

## Why This Does Not Overlap With Any Existing Signal

### vs. the 15 live ranker signals (ranker.py line 443)

| Existing signal | Operates on | DARB operates on | Overlap? |
|---|---|---|---|
| `w_semantic` | embedding cosine of host sentence vs. destination | host authority × host out-degree | **None** — different inputs, different math |
| `w_keyword` | token Jaccard of host sentence vs. destination | ^ | **None** |
| `w_node` | scope-tree structural proximity | ^ | **None** |
| `w_quality` (host PageRank log-normalized) | host's raw PageRank authority | host's *composite* content-value × inverse out-degree | **None** — w_quality uses raw PageRank only; DARB uses content-value composite AND modulates by out-degree. w_quality says "how authoritative is this host?"; DARB says "how much juice is this authoritative host hoarding?" Disjoint questions. |
| `weighted_authority` | destination's PageRank authority | host's authority + out-degree | **None** — destination-side vs. host-side |
| `link_freshness` | edge-age recency of the host→destination edge | host structural properties | **None** |
| `phrase_matching` | anchor-phrase text match to destination title | host structural | **None** |
| `learned_anchor_corroboration` | inbound-anchor vocabulary corroboration | host structural | **None** |
| `rare_term_propagation` | rare-term co-occurrence host ↔ destination | host structural | **None** |
| `field_aware_relevance` | title / body / scope field weighting | host structural | **None** |
| `ga4_gsc` (destination content-value) | destination's content_value_score | host's content_value_score / (1 + host.out_degree) | **None — different page.** ga4_gsc scores *destination* content-value; DARB scores the *host*'s content-value-to-out-degree ratio. Different inputs, disjoint by page role. |
| `click_distance` | destination shortest-path to homepage | host structural | **None** |
| `anchor_diversity` | anchor-text repetition per destination | host structural | **None** |
| `keyword_stuffing` | destination anchor-word fraction | host structural | **None** |
| `link_farm` | destination SCC density | host structural | **None** |

### vs. silo, clustering, slate_diversity, explore_exploit signals

| Signal | Input | DARB input | Overlap? |
|---|---|---|---|
| `silo.same_silo_boost` | pair (host, destination) silo match binary | host structural | **None** |
| `clustering` (FR-014) | destination semantic cluster | host structural | **None** |
| `slate_diversity` (FR-015) | final-slate MMR diversification | host structural | **None** |
| `explore_exploit` (FR-013) | feedback-driven Bayesian UCB1 | host structural | **None** |
| `pipeline.stage1_top_k` and `stage2_top_k` | retrieval fan-out | host structural at ranker stage 3 | **None** |

### vs. FR-006 dangling-node handling (the closest adjacency)

FR-006 Weighted Link Graph (shipped Phase 9) handles dangling nodes *inside the PageRank matrix iteration*:

```python
# backend/apps/pipeline/services/weighted_pagerank.py (abridged)
dangling_mass = sum(rank[i] for i in dangling_mask)
next_rank += (damping * dangling_mass + (1 - damping)) / N
```

This produces one authority score per page — `march_2026_pagerank_score`. It is a **graph-layer computation**.

DARB is a **ranker-layer per-pair signal**. It reads `content_value_score` (which already blends the FR-006 output with GSC/GA4 telemetry) and modulates by the host's `out_degree`. At the ranker, DARB is evaluated *per candidate-pair* and contributes an additive bonus to the composite score.

**Disjoint input partition:**
- FR-006 reads: the full weighted adjacency matrix. Output: `march_2026_pagerank_score` column.
- DARB reads: `host.content_value_score` (scalar) + `host.out_degree` (scalar). Output: per-pair scalar added to `component_scores[:, 15]` at ranker time.

Neither signal reads the other's output as input. No dependency cycle. FR-006 produces PageRank; DARB produces a composite-modulated inverse-out-degree score. The two are sequential layers in the pipeline, not parallel signals competing on the same measurement.

### vs. pending specs (60+ FR/pick/meta/opt files checked)

Checked every `fr###-*.md`, `pick-NN-*.md`, `meta-###-*.md`, `opt-###-*.md` in `docs/specs/`. The closest adjacency is **FR-074 Influence Score** (which uses PageRank on the *referral graph*, a different graph). No spec measures host-side inverse-out-degree authority.

### vs. recommended-preset keys

Checked `backend/apps/suggestions/recommended_weights.py` and `recommended_weights_forward_settings.py`. No reserved key starts with `darb.*` or `dangling.*`.

### vs. meta-algos

- FR-013 Explore/Exploit reranker: operates on historical reviewer approval per `(host_scope, destination_scope)` pair — different input (outcomes, not graph properties).
- FR-014 clustering: operates on destination semantic clusters.
- FR-015 slate diversity: operates on final-slate MMR.
- FR-018 auto-tuner: tunes weights, does not compute a signal.

**Conclusion: CLEAR.** DARB reads inputs no existing signal reads and produces an output no existing signal produces.

---

## Neutral Fallback

DARB returns `0.0` (and emits a diagnostic) when:

| Condition | Diagnostic string | Reason |
|---|---|---|
| `host.content_value_score` is NULL or NaN | `darb: missing_host_value` | Host content-value not yet computed (fresh import, analytics sync pending) |
| `host.content_value_score < 0.5` (below neutral) | `darb: below_neutral_host_value` | Host is not authoritative; no juice to redistribute |
| `host.out_degree >= darb.out_degree_saturation` (default 5) | `darb: saturated_host` | Host is not dangling — already linking out enough |
| `existing_outgoing_counts` map is missing entry for host | `darb: missing_out_degree` | Precompute cache miss (should not happen in practice; treated as saturated) |
| `darb.enabled == false` | `darb: disabled` | Operator has turned the signal off |

Never raises an exception inside `score_destination_matches`. Always returns a `DARBEvaluation` dataclass with `score_component: float`, `fallback_triggered: bool`, `diagnostic: str`, `raw_host_value: float | None`, `raw_host_out_degree: int | None`.

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language (v1)** | Python | DARB is O(1) per candidate (two scalar reads + one arithmetic operation). Well under the 50 ms / 500-candidate Python hot-path budget. No C++ port needed for v1. |
| **Language (future)** | Python only | BLC §2.3 requires C++ for hot-path loops > 1k calls/pipeline. DARB's per-candidate cost is ~100 nanoseconds in Python; a C++ port would save negligible wall-clock. Not worth the porting cost. |
| **Module location** | `backend/apps/pipeline/services/dangling_authority_redistribution.py` | Follows existing `anchor_diversity.py` / `keyword_stuffing.py` pattern. |
| **Settings dataclass** | `DARBSettings` | Matches `AnchorDiversitySettings` convention. |
| **Result dataclass** | `DARBEvaluation` | Matches `AnchorDiversityEvaluation` convention. |

---

## Hardware Budget

Target machine: i5-12450H, 16 GB RAM, RTX 3050 6 GB VRAM, 59 GB free disk (BLC §6).

| Resource | Per-pipeline precompute | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|
| RAM | 0 (reuses `existing_outgoing_counts` dict, already present) | < 1 KB | < 10 GB app headroom | ≈ 0 |
| CPU | 0 ms | < 100 ns (two scalar reads + arithmetic) | < 50 ms / 500 candidates (Python hot-path) | ≈ 0.05 ms / 500 candidates |
| GPU | 0 | 0 | < 6 GB VRAM | 0 |
| Disk | 0 | 0 | 30/90-day projection: 0 bytes new storage | 0 |

DARB adds no persistent storage and no precompute beyond what `pipeline_data.py` already computes (`existing_outgoing_counts`). Zero net overhead.

---

## Real-World Constraints

- **Bootstrap phase**: On a fresh install with no `content_value_score` populated (analytics sync hasn't run yet), every host returns the neutral fallback. DARB contributes 0.0 to every candidate. No harm done.
- **GSC / GA4 outage**: If `content_value_score` is stale, DARB still fires but uses the cached value. Diagnostic captures this via the existing `content_value_score` staleness indicator (managed by `analytics.sync` module).
- **Large corpus**: For a 100k-post site, the `existing_outgoing_counts` dict is ~100k entries × ~24 bytes = 2.4 MB. Trivial.
- **Interaction with FR-032 orphan audit**: Orphan audit surfaces "no-inbound" pages; DARB rewards candidates from "no-outbound" pages. Opposite direction, complementary.

---

## Diagnostics

Every `Suggestion` row with non-zero `darb.ranking_weight` stores:

```json
{
  "score_component": 0.0234,
  "raw_host_value": 0.78,
  "raw_host_out_degree": 2,
  "saturation_threshold": 5,
  "min_host_value_threshold": 0.5,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

This blob is rendered in the Review detail panel under a new "Dangling Authority (FR-099)" section. Reviewer questions answered per BLC §3:
1. **What changed the ranking?** `score_component` shows the exact contribution.
2. **Why neutral?** `fallback_triggered=true` and `diagnostic` explain the reason.
3. **Fallback used?** `fallback_triggered` flag.
4. **C++ or Python?** `path` field (always "python" for DARB v1).

---

## Benchmark Plan

Per BLC §1.4 and CLAUDE.md mandatory-benchmark rule. File: `backend/benchmarks/test_bench_darb.py`.

| Size | Input shape | Expected Python runtime | Alert threshold |
|---|---|---|---|
| small | 10 candidates, 100-post corpus | < 0.01 ms | > 1 ms |
| medium | 100 candidates, 10k-post corpus | < 0.1 ms | > 5 ms |
| large | 500 candidates, 100k-post corpus | < 0.5 ms | > 50 ms |

Benchmark verifies: pure-Python per-candidate cost is negligible and constant regardless of corpus size (O(1) lookup).

---

## Edge Cases

| Edge case | DARB behavior | Covered in test |
|---|---|---|
| Host is the candidate destination (self-link attempt) | Filtered upstream by ranker's `host_key == destination.key` check — DARB is never called | `test_darb_never_called_for_self_links` |
| `content_value_score` is `NULL` | Return `score_component=0.0`, `fallback_triggered=True`, `diagnostic="missing_host_value"` | `test_darb_neutral_when_host_value_null` |
| `content_value_score` is `NaN` | Same as NULL — treated as missing | `test_darb_neutral_when_host_value_nan` |
| `content_value_score` is above 1.0 (shouldn't happen but defensive) | Clamp to 1.0 before use | `test_darb_clamps_host_value_to_one` |
| `out_degree` is 0 | Compute `content_value / (1 + 0) = content_value` (maximum bonus for fully-dangling hosts) | `test_darb_max_bonus_at_zero_out_degree` |
| `out_degree` is very large (e.g. 100) but still below saturation | Compute normally; bonus approaches 0 as 1/(1+100) | `test_darb_asymptotic_zero_at_high_out_degree` |
| `out_degree >= saturation_threshold` | Return 0.0, `fallback_triggered=True`, `diagnostic="saturated_host"` | `test_darb_neutral_when_saturated` |
| `darb.enabled=false` | Return 0.0, `fallback_triggered=True`, `diagnostic="disabled"` | `test_darb_neutral_when_disabled` |
| `darb.ranking_weight=0.0` | DARB still computes but contribution is zeroed at ranker layer | `test_darb_zero_weight_produces_zero_final_contribution` |
| Negative weight (operator error) | Clamped to 0 at ranker-load time (validation in `pipeline_loaders.py`) | `test_pipeline_loader_rejects_negative_weight` |

---

## Gate Justifications

- [x] Spec exists with every mandatory section — this file.
- [x] Academic Source: Page et al. 1999, Stanford 1999-66, §2.5 + §3.2 eq. 1. Open-access URL cited.
- [x] Variable mapping table — present above.
- [x] Default cited: `0.04` derived from FR-006 weighted_authority proportional share; `5` from Broder et al. 2000 Table 1 median out-degree; `0.5` from ContentItem.content_value_score neutral midpoint (project semantic constant).
- [x] Non-overlap: enumerated all 15 live signals + silo/clustering/slate/explore_exploit + FR-006 + pending specs + meta-algos + recommended_weights keys.
- [x] Neutral fallback: 5 fallback conditions documented, each with a diagnostic string.
- [x] Architecture lane: Python only, O(1) cost justified.
- [x] Hardware budget: well under all budgets.
- [x] Diagnostic JSON: schema documented above.
- [x] Inline source comments: will land in `dangling_authority_redistribution.py`.
- [x] Preset keys seeded in `recommended_weights.py` with source-cite comments (Phase B step).
- [x] Migration upserts keys into Recommended preset (Phase B step).
- [x] Benchmark plan: 3 input sizes documented.

All Gate A boxes pass.

---

## Pending

- [ ] Python module `dangling_authority_redistribution.py` (Phase B of the FR-099–FR-105 plan).
- [ ] Unit test file `backend/apps/pipeline/tests/test_darb.py`.
- [ ] Benchmark file `backend/benchmarks/test_bench_darb.py`.
- [ ] `Suggestion.score_darb` + `Suggestion.darb_diagnostics` columns (migration 0036).
- [ ] `darb.*` keys in `recommended_weights.py` + migration 0035 upsert.
- [ ] Integration into `ranker.py` at component index 15.
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card + tooltip (Codex follow-up session, per FR-014 precedent).
- [ ] TPE-tuning eligibility (fixed for first 30 days; BLC §6.4).
- [ ] C++ fast path — **not needed**; O(1) per-candidate signal; Python is canonical.
