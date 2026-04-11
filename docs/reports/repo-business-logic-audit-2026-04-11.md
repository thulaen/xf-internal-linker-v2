# Research-Backed Business Logic Audit

Date: 2026-04-11

Scope:
- Live-code audit only. Findings below were verified against current implementation files, not just backlog text.
- Focused on import, ranking, reranking, attribution, and weight auto-tuning logic.
- Recommendations are constrained to avoid regressions, duplicated implementations, overlap with existing FRs, and avoidable performance loss.

## Executive Summary

The biggest current business-logic risks are not missing scaffolding. They are logic-quality gaps inside already-shipped paths:

1. the C# import lane is silently truncated after five pages per scope;
2. the feedback reranker claims inverse-propensity correction, but the stored signal is too coarse to support that claim;
3. the feedback reranker's C++ fast path and Python reference path do different math today;
4. attribution mixes two incompatible counterfactual stories and surfaces the weaker one in the UI;
5. auto-tuning still optimizes a four-number global summary instead of ranking quality in the live feature space.

These are all fixable without adding parallel subsystems. The safe path is to extend the existing FR-013, FR-017, and FR-018 implementations in place, keep neutral fallbacks, and ship each change behind diagnostics-first validation and benchmark gates.

Double-check outcome:
- all five findings still exist in current code;
- the first finding needed narrowing after a second repo pass:
  - the Django/Celery fallback importer already has checkpoints and configurable `import.max_pages`;
  - the hard five-page cap is specifically in the optional C# import owner path.

## Method

Code paths checked:
- `services/http-worker/src/HttpWorker.Services/PipelineServices.cs`
- `backend/apps/pipeline/tasks.py`
- `backend/apps/pipeline/tasks_import.py`
- `backend/apps/pipeline/services/feedback_rerank.py`
- `backend/extensions/feedrerank.cpp`
- `backend/apps/pipeline/tests.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/analytics/impact_engine.py`
- `backend/apps/analytics/views.py`
- `backend/apps/analytics/serializers.py`
- `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs`
- `frontend/src/app/analytics/analytics.component.html`
- `services/http-worker/src/HttpWorker.Services/Analytics/WeightTunerDataCollector.cs`
- `services/http-worker/src/HttpWorker.Services/Analytics/WeightObjectiveFunction.cs`
- `services/http-worker/src/HttpWorker.Services/Analytics/WeightTunerService.cs`
- `services/http-worker/src/HttpWorker.Core/Contracts/V1/WeightTuningContracts.cs`

Primary-source rule used for this report:
- each improvement is tied to a peer-reviewed paper with DOI;
- no recommendation below requires a brand-new overlapping feature;
- every recommendation is written as an extension of an existing code path.

## Findings

### 1. The C# import lane is artificially capped at five pages per scope

Code evidence:
- XenForo node import stops at `page <= 5`: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:31-87`
- XenForo resource import stops at `page <= 5`: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:89-142`
- WordPress import also stops at `page <= 5`: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:144-194`
- The C# lane is a real dispatch target when `RUNTIME_OWNER_IMPORT="csharp"`: `backend/apps/pipeline/tasks.py:414-453`
- That route is covered by tests as a supported runtime-owner mode: `backend/apps/pipeline/tests.py:4055-4069`

Second-pass narrowing:
- The Celery fallback importer does not have this exact flaw.
- It already has checkpoint-aware import state plus configurable `import.max_pages`: `backend/apps/pipeline/tasks_import.py:121-135`, `backend/apps/pipeline/tasks_import.py:176-203`, `backend/apps/pipeline/tasks_import.py:214-243`

Why this is a business-logic flaw:
- The ranker, graph, freshness, orphan audit, and attribution layers only see what the importer collected.
- A hard five-page cap in the C# lane creates silent corpus bias on larger forums and sites whenever that lane is enabled.
- That means downstream "quality" logic is being asked to optimize on incomplete inventory, which can distort PageRank, freshness, destination availability, and candidate generation.

Research basis:
- Chakrabarti, van den Berg, and Dom, "Focused crawling: a new approach to topic-specific Web resource discovery," *Computer Networks* 31(11-16), 1999. DOI: `10.1016/S1389-1286(99)00052-3`.
- The relevant takeaway is not "build a second crawler." It is that crawl-frontier prioritization and selective continuation outperform arbitrary depth truncation while using fewer resources.

Safe improvement:
- Bring the C# import lane up to parity with the existing Celery fallback importer.
- Keep the current single import contract and current clients. Do not add a second crawl system.
- Replace the fixed five-page cap in the C# lane with:
  - the same kind of configurable page budget already present in Django;
  - resumable checkpoint semantics where feasible;
  - freshness or priority ordering so the most valuable pages are imported first when a budget is hit.

Why this avoids regressions and performance loss:
- checkpointing improves coverage without forcing every run to become a full crawl;
- a page-budget cap can remain, but it should be operator-visible and resumable instead of hardcoded;
- no ranking formula changes are required, so this can be validated via corpus-growth and runtime benchmarks before it affects ranking behavior.

Implementation constraint:
- Treat this as an in-place C# lane parity correction, not a new FR that overlaps with existing import logic.

### 2. The feedback reranker does not have enough exposure detail to justify its inverse-propensity claim

Code evidence:
- The docstring claims presented-count can support inverse-propensity correction: `backend/apps/pipeline/services/feedback_rerank.py:51-61`
- The stored denominator is only daily presentation count at `(suggestion, user, presented_date)` granularity: `backend/apps/suggestions/models.py:726-771`
- No rank position, viewport visibility, or dwell exposure fields are stored in `SuggestionPresentation`: `backend/apps/suggestions/models.py:739-765`
- The exploit term is then discounted by `reviewed / presented` at scope-pair level: `backend/apps/pipeline/services/feedback_rerank.py:108-191`

Why this is a business-logic flaw:
- "Shown sometime that day" is not the same thing as "had a known examination probability."
- Position bias depends on where an item appeared and whether it was realistically seen.
- The current data is useful as a better proxy than generated-count, but it is still too coarse to support a strong inverse-propensity interpretation.

Research basis:
- Joachims, Swaminathan, and Schnabel, "Unbiased Learning-to-Rank with Biased Feedback," *WSDM 2017*. DOI: `10.1145/3018661.3018699`.
- The paper's key requirement is explicit propensity-aware correction for displayed items, not just aggregate "it was shown at least once" counts.

Safe improvement:
- Extend `SuggestionPresentation` rather than replacing it:
  - add rank position;
  - add a visible/impression-confirmed flag;
  - optionally add exposure duration bucket if the UI can provide it cheaply.
- Keep the existing daily dedup row as the neutral fallback if richer impression telemetry is unavailable.
- Upgrade FR-013 from scope-pair exposure proxying toward either:
  - self-normalized inverse propensity scoring; or
  - doubly robust correction once a simple reward model exists.

Why this avoids regressions and overlap:
- It extends the current FR-013 tables and reranker instead of creating a second feedback system.
- Old rows can still map to a neutral fallback path, so historic data does not become unusable.
- The scoring path can stay unchanged until enough richer exposure rows exist, which prevents cold-start regressions.

Performance note:
- extra fields on `SuggestionPresentation` are cheap compared with recomputing ranking signals;
- the expensive part is not storage, it is incorrect learning from weak exposure labels.

### 3. The feedback reranker's C++ fast path and Python path are not behaviorally equivalent

Code evidence:
- Python path computes and uses `exposure_prob`: `backend/apps/pipeline/services/feedback_rerank.py:147-173`
- The C++ batch input only passes `n_successes` and `n_totals`: `backend/apps/pipeline/services/feedback_rerank.py:195-231`
- The native kernel also uses only successes and totals, not exposure probability: `backend/extensions/feedrerank.cpp:22-39`
- The C++ diagnostics omit `presented`, `generated`, `exposure_prob`, and `score_exploit_raw`: `backend/apps/pipeline/services/feedback_rerank.py:233-258`
- The current parity test only checks the special case where `exposure_prob == 1.0`, so it does not catch the mismatch for partially exposed pairs: `backend/apps/pipeline/tests.py:850-898`

Why this is a business-logic flaw:
- The same ranking job can behave differently depending on whether the native extension is present.
- That is not just a code-quality issue. It means business logic changes with deployment state.
- It also weakens operator diagnostics because the fast path reports less information than the fallback.

Research basis:
- Same source as above: Joachims, Swaminathan, and Schnabel, *WSDM 2017*, DOI `10.1145/3018661.3018699`.
- Once a propensity term is part of the estimator, dropping it in the fast path changes the estimator, not just the implementation language.

Safe improvement:
- Make the Python formula the audited reference implementation.
- Port that exact formula to the native kernel, including any exposure term actually used.
- Require one parity benchmark and one parity test suite:
  - identical factors for representative sparse, medium, and dense exposure cases;
  - identical diagnostics schema from both paths.

Why this avoids regressions and performance loss:
- it removes environment-dependent ranking behavior;
- it preserves the current performance advantage of the native path;
- it avoids duplicated logic drift by keeping one formula and two implementations that must match.

Implementation constraint:
- This should be treated as an FR-013 correction, not as a new reranker or alternate fast path.

### 4. Attribution currently mixes two incompatible counterfactual models and exposes the weaker one to operators

Code evidence:
- Django claims a synthetic-control-style matched-control approach and selects nearest controls from same silo and content type: `backend/apps/analytics/impact_engine.py:31-138`
- Django then computes normalized deltas and stores control quality fields in `ImpactReport`: `backend/apps/analytics/impact_engine.py:233-345`
- The C# worker instead uses sitewide CTR trend as the counterfactual multiplier: `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs:55-113`
- The UI text shown to operators explicitly describes a "Global Control Baseline": `frontend/src/app/analytics/analytics.component.html:604-617`
- The search-impact API and detail API serialize `GSCImpactSnapshot`, not `ImpactReport`, so the matched-control confidence fields are not the primary operator-facing artifact: `backend/apps/analytics/views.py:1946-1959`, `backend/apps/analytics/views.py:1970-1992`
- `GSCImpactSnapshotSerializer` exposes click uplift and confidence-style CTR fields, but not `control_pool_size`, `control_match_count`, `control_match_quality`, or `is_conclusive`: `backend/apps/analytics/serializers.py:5-81`

Why this is a business-logic flaw:
- There are two different causal stories in one product:
  - matched page controls in Django;
  - global site CTR normalization in C# and in the UI.
- The Django side is also not actually a full synthetic control or BSTS implementation. It is nearest-neighbor matching on pre-period aggregates.
- That means the code comments, stored artifacts, and UI explanation are not aligned with each other or with the cited research.

Research basis:
- Abadie, Diamond, and Hainmueller, "Synthetic Control Methods for Comparative Case Studies," *Journal of the American Statistical Association* 105(490), 2010. DOI: `10.1198/jasa.2009.ap08746`.
- Brodersen et al., "Inferring causal impact using Bayesian structural time-series models," *The Annals of Applied Statistics* 9(1), 2015. DOI: `10.1214/14-AOAS788`.
- Both sources require a coherent counterfactual construction. The current split implementation does not provide one coherent operator-facing estimate.

Safe improvement:
- Pick one primary attribution contract and make all layers obey it.
- Best low-regression path:
  - keep the current Django matched-control layer as the operator-facing baseline if valid controls exist;
  - fall back to the sitewide trend model only when matched controls fail minimum quality thresholds;
  - surface which mode ran, plus control quality and conclusive/inconclusive state, in the UI.
- If the team wants actual synthetic control or BSTS later, implement that as an upgrade to FR-017, not as a parallel attribution system.

Why this avoids regressions and overlap:
- It reuses the current `ImpactReport` and `GSCImpactSnapshot` flow instead of inventing another attribution store.
- It removes semantic drift between comments, UI text, and stored output.
- It lets the stronger page-level control model win when available, while preserving the global fallback for sparse data.

Performance note:
- nearest-neighbor control matching is already present;
- exposing mode and quality metadata is cheap;
- a future true synthetic-control fit should stay offline or batched, not on the hot request path.

### 5. Auto-tuning still optimizes a four-metric global summary instead of ranking quality in the live feature space

Code evidence:
- The collector collapses the tuning window to four global aggregates: `services/http-worker/src/HttpWorker.Services/Analytics/WeightTunerDataCollector.cs:8-59`
- The weight-tuning contract only carries those four values plus an applied-count indicator: `services/http-worker/src/HttpWorker.Core/Contracts/V1/WeightTuningContracts.cs:17-34`
- The objective is a direct weighted sum of those four aggregate signals: `services/http-worker/src/HttpWorker.Services/Analytics/WeightObjectiveFunction.cs:7-50`
- The live ranker now uses far more than those four core weights, including weighted authority, freshness, phrase relevance, learned anchors, rare-term propagation, field-aware relevance, GA4/GSC, and click distance: `backend/apps/pipeline/services/ranker.py:330-570`
- After C# submits the challenger, Django evaluates promotion using those predicted quality scores rather than live per-query ranking outcomes: `backend/apps/pipeline/tasks.py:1930-2023`

Why this is a business-logic flaw:
- Ranking quality is about ordering candidates correctly within each host/destination decision context.
- The current tuner optimizes a convenient dashboard-level scalar, not a ranking metric.
- It also tunes only the original core weight subset while the live ranker has already expanded materially beyond that subset.

Research basis:
- Cao et al., "Learning to Rank: From Pairwise Approach to Listwise Approach," *ICML 2007*. DOI: `10.1145/1273496.1273513`.
- Joachims and Swaminathan, "Counterfactual Risk Minimization: Learning from Logged Bandit Feedback," *ICML 2015*. DOI: `10.5555/3045118.3045296`.
- The combined takeaway is that tuning should optimize ranking loss or counterfactual ranking utility over ranked lists, not a disconnected aggregate metric blend.

Safe improvement:
- Keep the current bounded optimizer shell if desired.
- Replace only the objective input:
  - evaluate candidate weight vectors on per-host ranked slates;
  - score them with approval-at-k, applied-at-k, NDCG@k, or a counterfactually corrected listwise metric;
  - keep the current four-weight scope at first if full-signal tuning is too large, but make the objective ranking-aware before expanding the parameter set.

Why this avoids regressions and reduced performance:
- It upgrades the objective before widening the search space.
- That means the first correction is "optimize the right thing" rather than "tune more knobs."
- Candidate evaluation can stay in batched offline tuning runs, so the online ranker stays unchanged until a challenger is validated.

Implementation constraint:
- Extend FR-018. Do not create a second tuner, second champion/challenger table, or alternate objective pipeline.

## Recommended Order Of Work

1. Fix FR-013 parity first.
   Reason: environment-dependent reranking is the most immediate correctness risk.
2. Upgrade FR-013 impression logging next.
   Reason: parity without better exposure data still leaves the estimator weak.
3. Unify FR-017 attribution semantics and UI wording.
   Reason: operators need one trustworthy causal story.
4. Remove the five-page import cap by adding checkpoints and budgets.
   Reason: better corpus quality improves multiple downstream systems at once.
5. Replace the FR-018 objective with ranking-aware evaluation.
   Reason: this has the highest strategic upside, but it should sit on top of cleaner attribution and feedback data.

## Non-Regression Rules For Any Follow-Up Implementation

The fixes above should only ship if all of these are respected:

1. No parallel implementations.
   Extend FR-013, FR-017, and FR-018 in place. Do not create second rerankers, second attribution pipelines, or second tuners.
2. Keep neutral fallbacks.
   Sparse-data paths must remain able to return neutral behavior instead of forcing a noisy score.
3. Require Python/C++ parity tests where native acceleration exists.
   Fast path and fallback must return the same math and the same diagnostics shape.
4. Use shadow mode before promotion.
   Compute new diagnostics and challenger outputs before switching operator-facing ranking or attribution labels.
5. Preserve current performance budgets.
   Hot-path work stays native or batched; richer attribution or tuning math must remain off the online request path.
6. Reuse existing tables and APIs where possible.
   Add columns or extend models before adding new stores.
7. Make the mode visible in the UI.
   Operators must be able to tell whether matched controls, global fallback, rich exposure, or fallback exposure was used.

## Primary Sources

1. Chakrabarti, S., van den Berg, M., and Dom, B. (1999). "Focused crawling: a new approach to topic-specific Web resource discovery." *Computer Networks*, 31(11-16), 1623-1640. DOI: `10.1016/S1389-1286(99)00052-3`
2. Joachims, T., Swaminathan, A., and Schnabel, T. (2017). "Unbiased Learning-to-Rank with Biased Feedback." *WSDM 2017*. DOI: `10.1145/3018661.3018699`
3. Abadie, A., Diamond, A., and Hainmueller, J. (2010). "Synthetic Control Methods for Comparative Case Studies: Estimating the Effect of California's Tobacco Control Program." *JASA*, 105(490), 493-505. DOI: `10.1198/jasa.2009.ap08746`
4. Brodersen, K. H., Gallusser, F., Koehler, J., Remy, N., and Scott, S. L. (2015). "Inferring causal impact using Bayesian structural time-series models." *The Annals of Applied Statistics*, 9(1), 247-274. DOI: `10.1214/14-AOAS788`
5. Cao, Z., Qin, T., Liu, T.-Y., Tsai, M.-F., and Li, H. (2007). "Learning to Rank: From Pairwise Approach to Listwise Approach." *ICML 2007*. DOI: `10.1145/1273496.1273513`
6. Swaminathan, A., and Joachims, T. (2015). "Counterfactual Risk Minimization: Learning from Logged Bandit Feedback." *ICML 2015*. DOI: `10.5555/3045118.3045296`

## Bottom Line

The repo already has a lot of serious logic in production paths. The highest-value work now is not adding more scoring ideas. It is tightening the existing decision systems so they:
- learn from complete enough data,
- use one coherent causal story,
- behave the same on native and fallback paths,
- and tune toward actual ranking quality rather than a convenient aggregate proxy.
