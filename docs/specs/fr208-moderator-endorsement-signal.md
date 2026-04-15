# FR-208 - Moderator Endorsement Signal

## Overview
When a forum moderator quotes, pins, stickies, or up-reacts to a user's post, that's an explicit positive signal that the user produces high-quality content. Adler & de Alfaro's content-driven reputation system formalises this kind of "trusted-actor endorsement" by giving extra weight to actions taken by users with already-high reputation. This signal counts mod endorsements per author and converts them into an additive author-trust boost.

## Academic source
**Adler, B. T. and de Alfaro, L. (2007).** "A Content-Driven Reputation System for the Wikipedia." *Proceedings of the 16th International Conference on World Wide Web (WWW 2007)*, pp. 261-270. DOI: `10.1145/1242572.1242608`. The "trusted-actor edit-survival weighting" in §3.3 — where edits by high-reputation users count more — is the basis for this signal applied to forum moderator endorsements.

## Formula
Let `endorsements(u)` = `{ e : actor(e) ∈ Mods ∧ target(e) ∈ posts(u) }` where endorsement events include:
- pin / sticky a post
- quote a post in a mod-flagged response
- mod-react with positive emoji (`+1`, `:check:`, `:star:`)
- mark as "best answer" / "accepted"

Each endorsement event `e` carries a weight by type (Adler & de Alfaro §3.3, Table 2):

| Event type | Weight `w_e` |
|---|---|
| Pin/sticky | 1.0 |
| Best-answer mark | 0.8 |
| Mod quote | 0.5 |
| Mod positive react | 0.3 |

Per-author endorsement score:
```
endorse_raw(u) = Σ_{e ∈ endorsements(u)}  w_e · trust_factor(actor(e))
```

`trust_factor` from FR-211 trust propagation (or `1.0` for any verified mod). Time-decayed variant:
```
endorse_decayed(u) = Σ_e  w_e · trust_factor(actor(e)) · exp(−β · age_days(e))
```
with `β = 0.005` (paper §3.4).

Final additive boost:
```
endorse_boost(u) = min(1.0, endorse_decayed(u) / endorse_norm),   endorse_norm = 10.0
```

## Starting weight preset
```python
"mod_endorsement.enabled": "true",
"mod_endorsement.ranking_weight": "0.0",
"mod_endorsement.weight_pin": "1.0",
"mod_endorsement.weight_best_answer": "0.8",
"mod_endorsement.weight_mod_quote": "0.5",
"mod_endorsement.weight_mod_react": "0.3",
"mod_endorsement.beta_decay": "0.005",
"mod_endorsement.endorse_norm": "10.0",
"mod_endorsement.use_time_decay": "true",
```

## C++ implementation
- File: `backend/extensions/mod_endorsement.cpp`
- Entry: `void compute_endorsement(const EndorsementEvent* events, int n_events, const int* mod_ids, int n_mods, const double* trust_factors, double* out_boost);`
- Complexity: `O(n_events · log(n_mods))` for the mod-membership lookup (sorted-array binary search)
- Thread-safety: per-author bucket update via atomic `fetch_add` on partial sums
- SIMD: `_mm256_exp_pd` for the decay term
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/mod_endorsement.py::compute_endorsement(...)` — pandas group-by with `np.exp` decay.

## Benchmark plan
| Events | C++ target | Python target |
|---|---|---|
| 10 K | < 5 ms | < 100 ms |
| 100 K | < 50 ms | < 1 s |
| 1 M | < 500 ms | < 10 s |

## Diagnostics
- Per-author `endorse_raw`, `endorse_decayed`, and `endorse_boost`
- Breakdown by event type (count per type per author)
- Top-10 most-endorsed authors
- Mod-set version & last-refresh timestamp
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with 0 endorsements → `boost = 0.0`, neutral
- Mod set empty (no moderators configured) → all `boost = 0.0`, flag `no_mods_configured`
- Endorsement event with unknown actor → skip event, flag `unknown_actor`
- Negative reaction (mod-flagged, mod-removed) → counts as `−w_e` (negative endorsement)
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 1` mod configured AND `≥ 10` endorsement events in corpus before scores are trusted; below this returns neutral `0.0`.

## Budget
Disk: <2 MB (event log)  ·  RAM: <40 MB at 1 M events

## Scope boundary vs existing signals
FR-208 does NOT overlap with FR-204 author H-index (counts upvotes from anyone, not just mods) or FR-207 edit-history density (author-self behaviour). It is *complementary* to FR-211 trust propagation — FR-208 uses mod identity directly; FR-211 propagates trust from any pre-trusted set. It also does not overlap with FR-118 TrustRank (page-level, not author-level).

## Test plan bullets
- unit tests: author with 1 pin (boost ≈ `0.10`), author with 5 best-answer marks (boost ≈ `0.40`)
- parity test: C++ vs Python `endorse_boost` within `1e-5`
- weight test: change `weight_pin` from `1.0` to `0.5` halves contribution from pins only
- decay test: 1-year-old endorsement contributes `≈ exp(−0.005·365) ≈ 0.16` of fresh weight
- integration test: ranking unchanged when `ranking_weight = 0.0`
- monotonicity test: adding a positive endorsement can only increase `boost`
