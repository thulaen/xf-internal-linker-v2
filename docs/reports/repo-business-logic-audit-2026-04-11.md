# Repo Status And Business Logic Audit

Date: 2026-04-11

Scope:
- Verified shipped vs pending work from repo docs against live code.
- Audited the ranking, import, attribution, and value-model paths.
- Backed improvement recommendations with primary academic or patent-adjacent research sources.

## Executive Summary

The repo is substantially implemented: the core 3-stage suggestion pipeline, review flow, graph tooling, telemetry sync, attribution path, co-occurrence layer, and C# worker infrastructure are all present in code.

The bigger issue is not "nothing is built"; it is "some important business rules are simpler or noisier than the roadmap language suggests." The highest-impact weaknesses are:

1. content import silently truncates large sources after five pages;
2. feedback reranking is still biased by presentation/exposure effects;
3. search-impact attribution uses weak control construction;
4. weight auto-tuning optimizes global averages instead of real ranking quality;
5. the value model still contains duplicated/noisy signals.

## Verified Done

- Core pipeline is live: `backend/apps/pipeline/services/pipeline.py:119-297`, `backend/apps/pipeline/services/ranker.py:355-830`.
- Review/apply flow is live: `backend/apps/suggestions/views.py:217-274`.
- Graph analysis is live, including coverage-gap analysis: `backend/apps/graph/views.py:628-777`, `frontend/src/app/graph/graph.component.html:981-1075`, `backend/apps/graph/tests.py:288-379`.
- Context-quality graph audit UI exists: `frontend/src/app/graph/graph.component.html:602-794`.
- Telemetry-driven destination scoring exists: `backend/apps/analytics/sync.py:879-975`.
- GSC attribution exists in both Django and C#: `backend/apps/analytics/impact_engine.py:17-239`, `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs:20-138`.
- Co-occurrence and value-model scoring exist: `backend/apps/cooccurrence/services.py:257-305`, `backend/apps/cooccurrence/services.py:446-556`.
- FR-036 appears implemented in code even though `AI-CONTEXT.md` still lists it as pending: `backend/apps/graph/views.py:628-777`, `frontend/src/app/graph/graph.component.ts:177-181,646-682`, `backend/apps/graph/tests.py:288-379`.

## Verified Partial Or Pending

- FR-020 is still pending. I found documentation and stale readiness flags, but no real hot-swap/runtime-registry implementation: `backend/apps/diagnostics/health.py:1457-1462`.
- FR-037 is only partially present. The backend exposes silo-leakage stats, but there is no matching frontend leakage-map view: `backend/apps/audit/views.py:56-112`; no matching frontend search hits for `silo-leakage`.
- FR-040, FR-042, and FR-044 are only seeded, not integrated into ranking logic. Their fields exist on `ContentItem`, but the diagnostics registry entries are still commented out and the current ranker does not score them:
  - `backend/apps/content/models.py:240-265`
  - `backend/apps/diagnostics/signal_registry.py:243-275`
  - `backend/apps/pipeline/services/ranker.py:355-568`
- A legacy R-based tuning stub still exists even though the current tuning path is C#: `backend/apps/pipeline/tasks.py:1441-1476`.
- The diagnostics readiness matrix is stale and under-reports shipped features (`FR-016` to `FR-019` are still marked `planned_only`): `backend/apps/diagnostics/health.py:1442-1462`.

## Business Logic Flaws And Research-Backed Improvements

### 1. Import coverage is artificially capped at five pages per source

Evidence:
- XenForo threads loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:35-38`
- XenForo resources loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:94-97`
- WordPress loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:151-157`

Why this is a business-logic problem:
- The whole product depends on having a representative corpus.
- A fixed `page <= 5` cap silently under-imports large forums/blogs, which then biases embeddings, PageRank, freshness, existing-link extraction, orphan detection, and downstream ranking.

Improve it by:
- Replacing the fixed page cap with a resumable frontier or continuation-token loop.
- Prioritizing pages/scopes by importance and freshness instead of stopping after an arbitrary depth.
- Persisting crawl checkpoints so imports can resume instead of restarting from page 1.

Research basis:
- Cho, Garcia-Molina, and Page, *Efficient Crawling Through URL Ordering* (1998): [archives.iw3c2.org/www7/proceedings/1919/com1919.htm](https://archives.iw3c2.org/www7/proceedings/1919/com1919.htm)

### 2. Feedback reranking claims exposure correction, but does not use real propensities

Evidence:
- Historical stats are aggregated only by `(host_scope, destination_scope)`: `backend/apps/pipeline/services/feedback_rerank.py:51-97`
- The so-called exposure correction is just `reviewed / generated`, not rank-position or display propensity logging: `backend/apps/pipeline/services/feedback_rerank.py:89-96`
- Final factor uses those aggregated counts directly: `backend/apps/pipeline/services/feedback_rerank.py:121-162`

Why this is a business-logic problem:
- Suggestions shown higher, shown more often, or shown in more review-friendly contexts will collect more approvals.
- The current reranker can therefore learn reviewer-interface bias, not true suggestion quality.
- Over time this can self-reinforce a narrow set of scope pairs.

Improve it by:
- Logging actual display/exposure propensities per suggestion, including position and whether the item was visible.
- Replacing the current proxy correction with inverse-propensity or doubly robust counterfactual learning-to-rank.
- Keeping the current Bayesian smoothing only as a prior, not as the whole debiasing story.

Research basis:
- Joachims, Swaminathan, and Schnabel, *Unbiased Learning-to-Rank with Biased Feedback* (2017): [microsoft.com/en-us/research/?p=398159](https://www.microsoft.com/en-us/research/?p=398159)

### 3. Search-impact attribution uses weak counterfactual construction

Evidence:
- Django-side control group is "same silo, first 10 items, no applied links in window": `backend/apps/analytics/impact_engine.py:109-123`
- Normalization is then a simple control multiplier ratio: `backend/apps/analytics/impact_engine.py:194-237`
- C# attribution uses sitewide CTR trend as the counterfactual multiplier: `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs:55-113`

Why this is a business-logic problem:
- Same-silo pages are not necessarily matched on baseline traffic, seasonality, content age, or SERP/query mix.
- Sitewide CTR is too coarse for page-level causal claims.
- The system can over-credit or under-credit a link when the destination sits inside a changing cohort.

Improve it by:
- Building matched controls from pre-intervention behavior, not just shared silo.
- Moving attribution toward Bayesian structural time-series or synthetic-control style counterfactuals.
- Returning uncertainty bands and "insufficient control quality" states when the match is weak.

Research basis:
- Brodersen et al., *Inferring causal impact using Bayesian structural time-series models* (2015): [research.google/pubs/pub41854](https://research.google/pubs/pub41854)
- Abadie, Diamond, and Hainmueller, *Synthetic Control Methods for Comparative Case Studies* (2007/2010): [nber.org/papers/t0335](https://www.nber.org/papers/t0335)

### 4. Auto-tuning optimizes a global scalar, not actual ranking quality

Evidence:
- The tuner only collects four global aggregate signals: `services/http-worker/src/HttpWorker.Core/Contracts/V1/WeightTuningContracts.cs:18-33`
- The collector returns a single average per signal for the whole lookback window: `services/http-worker/src/HttpWorker.Services/Analytics/WeightTunerDataCollector.cs:35-58`
- The optimizer score is just a weighted sum of those four aggregates: `services/http-worker/src/HttpWorker.Services/Analytics/WeightObjectiveFunction.cs:44-50`

Why this is a business-logic problem:
- A ranking system is judged by how it orders candidates within each decision context, not by one global average per metric.
- With the current objective, whichever aggregate metric is largest can attract weight even if actual per-suggestion ranking gets worse.
- This is closer to metric blending than learning-to-rank.

Improve it by:
- Optimizing per-suggestion or per-destination ranking metrics such as NDCG, approval lift, or verified-apply lift.
- Using listwise or counterfactual ranking objectives rather than a single global weighted-average score.
- Keeping the current bounded optimizer as the outer search wrapper if desired, but giving it a ranking-aware objective.

Research basis:
- Cao et al., *Learning to Rank: From Pairwise Approach to Listwise Approach* (2007): [microsoft.com/en-us/research/?p=153086](https://www.microsoft.com/en-us/research/?p=153086)
- Joachims, Swaminathan, and Schnabel, *Unbiased Learning-to-Rank with Biased Feedback* (2017): [microsoft.com/en-us/research/?p=398159](https://www.microsoft.com/en-us/research/?p=398159)

### 5. The value model still mixes duplicated and weakly calibrated signals

Evidence:
- `traffic_signal` and `engagement_signal` are currently the same value: `backend/apps/cooccurrence/services.py:469-475`
- Co-occurrence scoring uses Jaccard normalized by the single sitewide maximum and does not score with `lift` even though it is stored: `backend/apps/cooccurrence/services.py:257-305`
- The final value score linearly combines those signals as if they were independent: `backend/apps/cooccurrence/services.py:521-555`

Why this is a business-logic problem:
- The model is presented as a richer multi-signal value layer, but one signal is duplicated and one is based on an outlier-sensitive normalization rule.
- This can overstate popular pairs, understate statistically surprising pairs, and make the score harder to interpret.

Improve it by:
- Splitting true engagement into its own separately measured feature instead of aliasing traffic.
- Replacing max-normalized Jaccard with a significance-aware association measure plus minimum-support/shrinkage logic.
- Calibrating the value-model output before it is consumed as a pre-ranking score.

Research basis:
- Dunning, *Accurate Methods for the Statistics of Surprise and Coincidence* (1993): [aclanthology.org/J93-1003/](https://aclanthology.org/J93-1003/)

## Priority Order

If this were my next-work queue, I would do it in this order:

1. Fix import coverage and checkpointing.
2. Fix attribution counterfactuals.
3. Fix feedback-rerank debiasing.
4. Replace the tuner objective with ranking-aware evaluation.
5. Clean up the value model and remove duplicated signals.
6. Reconcile status drift in `AI-CONTEXT.md` and `backend/apps/diagnostics/health.py`.

## Bottom Line

The repo is much farther along than a "prototype" and already contains a large amount of real product logic. The main risk now is not missing scaffolding. It is silent statistical bias: incomplete imports, biased feedback reuse, weak attribution controls, and objective functions that optimize the wrong target.
