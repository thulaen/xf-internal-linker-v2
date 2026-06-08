# FR — Rust Ranking Decision Engine

[SPEC FRESHNESS: reviewed_at=2026-06-07 next_review=2026-07-07]
[SPEC CITED: feature=ranking-decision-engine kind=technical_doc id=ISO/IEC/IEEE-42010:2022 verified_at=2026-06-06]
[SPEC CITED: feature=ranking-decision-engine kind=academic_paper id=doi:10.1007/s10618-008-0114-1 verified_at=2026-06-07]
[SPEC CITED: feature=ranking-decision-engine kind=academic_paper id=doi:10.1145/2094072.2094078 verified_at=2026-06-07]
[SPEC CITED: feature=ranking-decision-engine kind=academic_paper id=doi:10.1016/j.infsof.2018.02.010 verified_at=2026-06-07]

## Summary

`RankingDecisionEngine` is the Rust authority for live ranking decisions. Python loads candidate
data and stores results; Rust scores candidates, validates profiles, enforces the memory budget,
orders the final list, and returns plain-English explanations.

Given candidate links, a ranking profile, and a site policy,
When the engine scores and ranks them,
Then every score is bounded, explained, versioned, memory-checked, and reversible.

The engine has two layers. Layer 1 (the kernel sections below) is the Rust scoring kernel, already
built. Layer 2 (added 2026-06-07) is the Django policy authority around it: one service that
decides which weights are live, one immutable record per weight change, and one entry point that
live scoring, shadow evaluation, and replay all share. Layer 2 exists because the 2026-06-07 audit
found four independent code paths writing ranking weights with no shared lock, no documented
precedence, and zero production callers for the Rust kernel.

Given presets, manual edits, and autotuner promotions all want to change ranking weights,
When any of them commits a change,
Then exactly one resolver applies it under one lock, producing one numbered, never-edited policy
record that every later ranking decision can be traced back to.

## Source Of Truth

- **Architecture description:** ISO/IEC/IEEE 42010:2022, *Software, systems and enterprise —
  Architecture description*. This spec names the concerns, boundaries, and responsibilities.
- **Module ownership:** Parnas 1972, "On the Criteria To Be Used in Decomposing Systems into
  Modules," CACM 15(12), doi:10.1145/361598.361623. The engine hides scoring and governance
  decisions behind one Rust public surface.
- **Floating-point checks:** IEEE 754-2019, *IEEE Standard for Floating-Point Arithmetic*. Score
  validation pins finite values, bounds, and tolerance rather than relying on implicit platform
  behavior.
- **Learning-to-rank baseline:** Liu 2009, *Learning to Rank for Information Retrieval*,
  doi:10.1561/1500000016. The first slice preserves the existing linear weighted feature blend.
- **Rust/Python boundary:** PyO3 <https://pyo3.rs/> and maturin <https://www.maturin.rs/>. The
  crate exposes typed Python-callable records through a Rust implementation.
- **Controlled experiments and the overall evaluation criterion:** Kohavi, Longbotham,
  Sommerfield, Henne 2009, "Controlled experiments on the web: survey and practical guide," Data
  Mining and Knowledge Discovery 18(1), doi:10.1007/s10618-008-0114-1. Defines the single agreed
  success metric (the "overall evaluation criterion") and why a ranking change needs a comparison
  group before full exposure.
- **Online evaluation of rankers:** Chapelle, Joachims, Radlinski, Yue 2012, "Large-scale
  validation and analysis of interleaved search evaluation," ACM Transactions on Information
  Systems 30(1), Article 6, doi:10.1145/2094072.2094078. Evidence that offline metrics alone can
  mis-order candidate rankers; this motivates the shadow pass.
- **Shadow deployments:** Schermann, Cito, Leitner, Zdun, Gall 2018, "We're doing it live: A
  multi-method empirical study on continuous experimentation," Information and Software Technology
  99, pp. 41–57, doi:10.1016/j.infsof.2018.02.010. Names and validates the practice of running a
  candidate configuration beside the live one without user exposure.
- **Configuration debt and entanglement:** Sculley et al. 2015, "Hidden Technical Debt in Machine
  Learning Systems," NeurIPS 28,
  <https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html>.
  The sections "Entanglement" ("Changing Anything Changes Everything") and "Configuration Debt"
  name the risks Layer 2 removes: many writers to live ML configuration with no single owner.
- **Wolfram offline oracle:** Wolfram Technology Integration
  <https://www.wolfram.com/technology-integration/>, WSTP documentation
  <https://reference.wolfram.com/language/tutorial/IntroductionToWSTP.html>, wolframscript
  documentation <https://reference.wolfram.com/language/ref/program/wolframscript.html.en>, and
  the Rust `wstp` crate <https://docs.rs/wstp/latest/wstp/>. Wolfram is test-only, never live
  scoring.

## Architecture Lane

Rust owns live scoring and validation. Python owns Django, data loading, offline training, and
storage. The Python wrapper imports `extensions.ranking_decision_engine`; missing Rust is a loud
error with no Python fallback.

The Rust crate is split into these modules:

- `ranking_schema`: typed request, profile, policy, result, and explanation records.
- `ranking_features`: feature normalization and missing-value policy.
- `ranking_memory`: 2 GB budget estimates and hard refusal before scoring.
- `ranking_core`: bounded scoring, deterministic ordering, and top-N retention.
- `ranking_profiles`: profile safety checks.
- `ranking_governance`: machine verdicts with reason codes and plain-English text.
- `ranking_explain`: per-candidate explanation lookup.
- `wolfram_oracle`: test-only fixture notes and future Wolfram integration.

Layer 2 is plain Python + Postgres. It runs at change-event cadence (operator clicks and monthly
tuner runs), never on a hot path, so per `RUST-FIRST.md` it stays in Python. It lives in
`apps/suggestions` (beside `WeightPreset`, `WeightAdjustmentHistory`, and `RankingChallenger`)
behind that module's `api.py`; the pipeline reads it only through that surface. The approval
workflow (slice 6) is written so it can move into the `governance` module from
`docs/MODULAR-MONOLITH.md` once that module exists on disk, without schema change.

## Public Interface

- `rank_candidates(candidates, profile, policy) -> RankedBatch`
- `validate_profile(candidate, baseline, max_movement) -> GovernanceVerdict`
- `memory_estimate(candidate_count, max_bytes) -> MemoryEstimate`
- `explain(batch, decision_id) -> str | None`

## Why A Central Authority — Problem Evidence (2026-06-07 audit)

- Four code paths write ranking weights to `AppSetting`: preset apply
  (`WeightPresetViewSet.apply`), the per-field settings views, challenger promotion
  (`evaluate_weight_challenger`), and rollback (`check_weight_rollback`). Only the last two take
  the weight lock; `backend/apps/suggestions/views.py` contains zero lock usage, so a manual write
  during a promotion is a last-write-wins race.
- The audit trail is split: presets, promotions, and rollbacks write `WeightAdjustmentHistory`,
  while manual field edits write only per-key `AuditEntry` rows.
- No document states precedence between preset, manual edit, and autotuner —
  `fr018-auto-tuned-ranking-weights.md`, `RANKING-GATES.md`, and `AUTOTUNER-FUTURE-AWARENESS.md`
  are all silent on it.
- The blend-weight tuner (FR-018) and the meta-parameter tuner (FR-018b) run on the same monthly
  schedule and optimize independently; each treats the other's parameters as fixed, and the
  meta-challenger judge (`evaluate_and_promote`) is imported but has no implementation.
- The Rust kernel above is built and tested but has zero production callers.

These are the "Entanglement" and "Configuration Debt" risks of Sculley et al. 2015, present in
this codebase today.

## Policy Authority — Design (Layer 2)

**`RankingPolicy` (new model, `apps/suggestions`).** One immutable row per effective weight
configuration: a monotonically increasing `version`, `resolved_weights` (the full blend +
secondary weight map), `meta_params`, `source` (`preset` / `manual` / `auto_tune` / `rollback` /
`bootstrap`), references to the preset or challenger that caused it, `parent_policy`,
`content_hash` for skip-if-unchanged dedupe, `engine_version`, `status` (`draft` / `live` /
`superseded` / `rolled_back`), the author, and a plain-English `reason`. Exactly one row has
`status='live'` at any time.

**`PolicyResolver` (new service, `apps/suggestions`).** The only writer. Resolution order, lowest
to highest: recommended defaults → system preset → applied preset → manual key overrides →
promoted challenger. Every commit runs under the existing `with_weight_lock("medium")`, validates
bounds against `tunable_registry.py`, writes one `WeightAdjustmentHistory` row (all sources,
manual field edits included), refreshes the `AppSetting` cache, and supersedes the previous live
policy. `apply_weights()` in `weight_preset_service.py` becomes the resolver's private write
primitive.

**Callers after the migration.** Preset apply, every per-field settings view, challenger
promotion, and rollback all delegate to `PolicyResolver.commit(change)`. A direct
`AppSetting.update_or_create` on a ranking key outside the resolver becomes a code-review reject
and a drift-healer alert at runtime.

**Pipeline linkage.** Each `PipelineRun` stores the live `policy` foreign key next to the existing
`config_snapshot` (which is kept as an independent record). Every suggestion already links to its
run, so every decision traces to one numbered policy.

## Mapping: Paper Variables → Code Variables

| Paper notation / concept | Code variable |
|---|---|
| Overall evaluation criterion (Kohavi 2009, terminology section) | challenger quality: BCE-derived `predicted_quality_score` plus NDCG@10 from `ndcg_eval.py`; the shadow pass adds rank-swap count and top-10 churn |
| Treatment vs control exposure (Kohavi 2009) | live policy vs shadow policy inside the same run — the candidate gets zero reviewer exposure |
| Interleaved comparison (Chapelle 2012) | per-run shadow delta report. Divergence: no user-facing interleaving — reviewers, not searchers, consume the output, so the comparison is computed, never shown |
| Dark launch / shadow deployment (Schermann 2018) | the `ranking_policy.shadow_enabled` pass writing `ShadowComparison` rows |
| Sequential test thresholds α, β (Wald-style SPRT) | existing `ChallengerSPRTEvaluator(alpha=0.05, beta=0.10)` — unchanged, now also fed shadow metrics |
| `max_movement` (kernel `validate_profile`) | `_DRIFT_LIMIT_PER_RUN = 0.05` in `weight_tuner.py` — unchanged |

## Researched Starting Point

Every new key seeds via a `get_or_create` migration, default ON (`DEFAULT-ON-RULE.md`), and
carries `# AUTOTUNER-EXCLUDED: operational toggle, not a ranking weight` (Gate A13):

- `ranking_policy.enabled = true` — the policy layer is wired end-to-end from slice 1.
- `ranking_policy.shadow_enabled = true` — Schermann 2018 reports shadow runs as the lowest-risk
  experimentation practice because users never see the candidate; the cost here is one extra
  weighted-sum pass inside the kernel's existing budget.
- `ranking_policy.shadow_window_days = 14` — equals the FR-018 rollback-watchdog window so
  promotion evidence and rollback evidence cover the same period (internal-consistency
  justification, not a round-number default).
- `ranking_policy.replay_max_rows` — derived from the hardware-profile tier
  (`apps/pipeline/services/hardware_profile.py`) per `HARDWARE-PROFILES.md`; no hardcoded batch
  size.

## Why This Does Not Overlap With Any Existing Signal

This spec adds zero score terms; the 15-component composite and every live signal are unchanged.
Adjacent non-signal surfaces, one line each:

- `weight_preset_service.apply_weights()` — absorbed as the resolver's private write primitive,
  not duplicated.
- `WeightAdjustmentHistory` — kept; it becomes resolver-written only, closing the manual-edit gap.
- `RankingChallenger` + `ChallengerSPRTEvaluator` — kept as proposal and judge; the resolver
  executes promotions instead of the task writing keys directly.
- `PipelineRun.config_snapshot` — kept; the policy foreign key adds identity and lineage on top.
- `meta_hpo_eval.py` — reused by replay as the in-memory re-scoring path; no second scorer is
  written.
- `ndcg_eval.py` — reused as the metric provider for shadow reports.
- FR-013 / FR-014 / FR-015 meta-algorithms — untouched; they read their parameters exactly as
  today.
- `tunable_registry.py` — the resolver validates every commit against its bounds.
- Legacy C++ `extensions.scoring` composite — superseded by the kernel wiring slice per ADR 0007;
  exactly one scoring path exists at every commit.

## Neutral Fallback

- No policy rows yet → the resolver bootstraps policy v1 from the current live `AppSetting` state
  and emits the diagnostic `policy: bootstrapped from live settings`.
- Rust kernel missing → loud `RankingDecisionEngineUnavailableError`, no Python fallback
  (ADR 0007); slices 1–2 do not touch the scoring path, so they are unaffected.
- Shadow enabled with no pending challenger → no-op with the diagnostic `shadow: no candidate`.
- Replay request naming an unknown run or policy → plain-English 404, no partial result.
- Out-of-band `AppSetting` edit → the drift healer restores the cache from the live policy and
  raises an OperatorAlert naming the changed keys.

## Memory Budget

The live Rust runtime budget is 2 GB by default. Each request estimates memory before scoring:

- fixed request overhead;
- per-candidate input, score, contribution, and explanation storage;
- top-N result storage.

If the estimate exceeds the request budget, Rust returns a blocked result with
`split batch required`. The engine does not start scoring an oversized request.

## 10 Million Verified Cases

The milestone is 10 million verified generated cases, not 10 million hand-written lines. The corpus
will be streamed and compressed so tests do not load it all into memory.

The first slice adds deterministic Rust tests for memory refusal, bounded scores, sorting, profile
validation, and explanation lookup. Later slices add generated fixtures, Wolfram-derived expected
values, and real pipeline regression cases.

## Hardware Budget — Layer 2

Target machine per `docs/BUSINESS-LOGIC-CHECKLIST.md` §6 (i5-12450H, 16 GB RAM, RTX 3050, 512 GB
NVMe):

- Policy resolve: a handful of Postgres reads plus two writes per change event; change events
  arrive at operator/monthly cadence; < 10 ms each; never a hot path.
- `RankingPolicy` growth: one row per real change with hash-skip when nothing changed
  (`NO-DUPLICATES.md`); the historical change rate in `WeightAdjustmentHistory` is tens of rows per
  year → < 1 MB at 90 days.
- Shadow pass: one extra composite multiply per batch inside the kernel's existing
  < 5 ms / 500-candidate budget; `ShadowComparison` is one summary row per (run, challenger),
  superseded per `NO-DUPLICATES.md` → < 10 MB at 90 days.
- Replay: on demand, capped by `ranking_policy.replay_max_rows`, transient RAM < 1 MB at the
  default tier (row cap × 15 float32 components); no GPU anywhere in this feature.

## Real-World Constraints

- All four weight writers migrate to the resolver in one slice. A partial migration leaves two
  live write paths at once, which is worse than today's state.
- Replay re-weights the per-signal scores already persisted on each suggestion. It cannot
  recompute embeddings for old content (embedding versions move on), and the API response states
  this limit explicitly.
- Shadow evidence that depends on Google Search Console arrives on that service's reporting delay
  — the same limit the FR-018 rollback watchdog already absorbs.
- The resolver uses the existing `with_weight_lock("medium")`; the worst-case wait stays inside
  the current 60-second-retry, roughly one-hour-patience envelope.
- `AppSetting` stays as the materialized live-weight cache that `pipeline_loaders.py` reads, so
  slices 1–2 change zero scoring behavior; the policy table adds identity and lineage on top.

## Edge Cases

- Missing or invalid feature values normalize to the neutral value `0.5` and are reported.
- Non-finite scores block validation.
- Weights below `0.01` are blocked so a signal cannot be silently disabled.
- Weight sums must stay within the declared tolerance of `1.0`.
- Requests over budget return `blocked` before scoring.
- `top_n = 0` returns an empty ranked list and a ready status.

Layer 2 additions:

- Two writers race (an operator applies a preset during a tuner promotion): the resolver lock
  serializes them; the second writer re-resolves on top of the first's policy; both land as
  separate numbered policies with correct lineage, and both appear in `WeightAdjustmentHistory`.
- Resolved weights identical to the live policy (hash match): skip-if-unchanged — no new row.
- Rollback never edits a row: it creates a new policy whose contents equal the chosen baseline.
- A policy row is never deleted while any `PipelineRun` references it (protected foreign key).
- Replay across different `engine_version` values refuses by default and requires an explicit
  override flag, because score semantics can differ between kernel versions.
- An out-of-band `AppSetting` edit that bypasses the resolver is healed from the live policy and
  raises an OperatorAlert naming the changed keys.

## Diagnostics

Each scored candidate includes:

- raw normalized feature values;
- per-feature weighted contributions;
- final score;
- decision id;
- plain-English explanation;
- engine version.

Layer 2 adds, each with a plain-English hover per `PLAIN-ENGLISH-HELPER-RULE.md`:

- Run detail: the live policy id, version, and source chain (which preset, which manual edits,
  which challenger produced it).
- Policy timeline: every policy with author, source, reason, and per-key delta.
- Shadow report per run: NDCG@10 live vs candidate, rank-swap count, and top-10 churn.
- Replay response: old/new score and per-component contribution deltas via the kernel's
  `explain()`.

## Behavior (BDD)

Given a pending weights challenger is being promoted,
When an operator applies a preset at the same moment,
Then both changes serialize through the resolver lock,
And two policy rows exist with correct lineage,
And both appear in `WeightAdjustmentHistory`.

Given a pending challenger exists and `ranking_policy.shadow_enabled` is true,
When a pipeline run scores candidates,
Then the reviewer-visible order comes from the live policy only,
And a `ShadowComparison` row stores the candidate-vs-live deltas for the SPRT evaluator.

Given a finished run and any stored policy id,
When the operator calls the replay endpoint,
Then re-weighted scores and rank deltas return without any database write.

Given no policy rows exist yet,
When the resolver first runs,
Then policy v1 is created from the current live settings,
And the run diagnostic records `policy: bootstrapped from live settings`.

## Slices

1. `RankingPolicy` model + `PolicyResolver` + migrate all four writers + bootstrap + drift
   healer.
2. `PipelineRun.policy` foreign key + policy timeline API and a minimal UI table.
3. Route the live composite path through `rank_candidates()`; record `engine_version` per policy;
   retire the legacy C++ `extensions.scoring` composite per ADR 0007 in the same slice so exactly
   one scoring path exists at every commit.
4. Shadow pass + `ShadowComparison` + the SPRT evaluator consumes shadow metrics; implement the
   meta-challenger judge (today's `evaluate_and_promote` import has no implementation).
5. Replay endpoint + review-page panel.
6. Approval state machine on policy transitions (draft → approved → live) with a recorded
   approver and reason; OperatorAlert on every automatic promotion.

Each slice follows strict test-first development with the five coverage layers, keeps functions
≤ 50 lines, and lands with its benchmark.

## Benchmark Plan

pytest-benchmark, three input sizes each (`docs/BUSINESS-LOGIC-CHECKLIST.md` §1.4), in
`backend/benchmarks/`:

- `test_bench_policy_resolver.py` — 1 / 10 / 100 sequential resolver commits.
- `test_bench_shadow_pass.py` — 500 / 5,000 / 50,000 candidates; pass condition: < 5% added
  pipeline wall time.
- `test_bench_replay.py` — 100 / 1,000 / `replay_max_rows` suggestions.

Rust kernel benchmarks are unchanged.

## Test Plan

- Rust unit tests: `cargo test -p ranking_decision_engine`
- Rust benchmark smoke: `cargo bench -p ranking_decision_engine --bench bench_ranking_decision_engine`
- Python loader test: `docker compose exec -T backend python manage.py test apps.pipeline.test_ranking_decision_engine_loader`
- Layer 2 (from slice 1): `docker compose exec -T backend python manage.py test apps.suggestions.tests_ranking_policy apps.suggestions.tests_policy_resolver`

## Gate Justifications

- A6 (non-overlap) is argued against meta-algorithms and infrastructure rather than signals: this
  spec adds zero score terms, so there is no signal to disambiguate.
- A9/A10 (Recommended-preset keys + migration): the Layer-2 keys are operational toggles, not
  ranking weights; they seed via a `get_or_create` migration with the citations above and do not
  enter the Recommended preset's weight set.
- A11 (per-signal Suggestion columns): not applicable — no new signal; diagnostics land at run and
  policy level instead.
- A13 (tunable registry): the new keys carry `# AUTOTUNER-EXCLUDED: operational toggle, not a
  ranking weight` in the migration, so the registry hook passes without registry rows.

## Pending

- Interleaving (Chapelle 2012) is consciously out of the design: reviewers, not live searchers,
  consume the output, so there is no results page on which to interleave. Shadow + SPRT covers the
  need. Reopen only if live user exposure ever exists.
- The `governance`-module placement for slice 6 waits on the modular-monolith rollout; until that
  module exists, the code ships inside `apps/suggestions` behind `api.py`.
- `FEATURE-REQUESTS.md` registration and the per-slice paper-trail entries must be filed from a
  Docker-capable session (`manage.py defer_work`); the sandbox that authored this revision had no
  Docker access.

## Citations

- ISO/IEC/IEEE 42010:2022 — *Software, systems and enterprise — Architecture description*.
- Parnas 1972 CACM — "On the Criteria To Be Used in Decomposing Systems into Modules."
  doi:10.1145/361598.361623.
- IEEE 754-2019 — *IEEE Standard for Floating-Point Arithmetic*.
- Liu 2009 — *Learning to Rank for Information Retrieval*. doi:10.1561/1500000016.
- PyO3 user guide — Rust bindings for Python. <https://pyo3.rs/>
- maturin user guide — Rust Python package builds. <https://www.maturin.rs/>
- Wolfram Technology Integration — integration options including wolframscript and WSTPServer.
  <https://www.wolfram.com/technology-integration/>
- Wolfram WSTP documentation — two-way communication with external programs.
  <https://reference.wolfram.com/language/tutorial/IntroductionToWSTP.html>
- WolframScript documentation — command-line Wolfram Engine execution and kernel path settings.
  <https://reference.wolfram.com/language/ref/program/wolframscript.html.en>
- Rust `wstp` crate documentation — Rust support for WSTP and licensing notes.
  <https://docs.rs/wstp/latest/wstp/>
- Kohavi, Longbotham, Sommerfield, Henne 2009 — "Controlled experiments on the web: survey and
  practical guide." Data Mining and Knowledge Discovery 18(1). doi:10.1007/s10618-008-0114-1.
- Chapelle, Joachims, Radlinski, Yue 2012 — "Large-scale validation and analysis of interleaved
  search evaluation." ACM TOIS 30(1), Article 6. doi:10.1145/2094072.2094078.
- Schermann, Cito, Leitner, Zdun, Gall 2018 — "We're doing it live: A multi-method empirical
  study on continuous experimentation." Information and Software Technology 99, pp. 41–57.
  doi:10.1016/j.infsof.2018.02.010.
- Sculley et al. 2015 — "Hidden Technical Debt in Machine Learning Systems." NeurIPS 28.
  <https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html>
