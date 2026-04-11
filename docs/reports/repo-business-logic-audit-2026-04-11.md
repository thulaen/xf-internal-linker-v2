# Repo Status And Business Logic Audit

Date: 2026-04-11

Scope:
- Re-checked repo status from live code, not just backlog text.
- Focused the logic audit on the current import, feedback, attribution, ranking, and value-model paths.
- Kept only findings that still hold up in the current code.
- Backed each improvement recommendation with primary academic sources.

## Executive Summary

The repo is much farther along than the backlog text alone suggests. The core pipeline, manual review flow, graph tooling, telemetry sync, attribution plumbing, and co-occurrence/value-model layer are all live in code.

The main status drift is that the docs still count `FR-036` as pending, but the code already ships a working coverage-gap endpoint, tests, and UI copy for it. A few other items are only partially true in the docs as well: `FR-040`, `FR-042`, and `FR-044` are no longer just "future keys" because model fields now exist, but they are still not wired into scoring.

The highest-impact current business-logic weaknesses are:

1. import coverage is still silently capped at five pages per source;
2. feedback reranking still uses a weak exposure proxy instead of real propensities;
3. attribution currently mixes two different counterfactual stories, one matched and one global;
4. FR-018 auto-tuning still optimizes four global averages, not actual ranking quality.

One important correction to the previous version of this report: the older value-model criticism is now stale. Co-occurrence no longer uses max-normalized Jaccard, and traffic and engagement are now separate fields.

## Code-Verified Status

### Documented baseline

The continuity docs currently say the project has `31` completed FRs, `5` partial FRs, and `60` pending FRs, and they still list `FR-036` as pending:

- `AI-CONTEXT.md:232-260`
- `FEATURE-REQUESTS.md:799-860`

That baseline is useful, but it is no longer fully aligned with the code.

### Code-verified implemented

- Core pipeline wiring is live: `backend/apps/pipeline/services/pipeline.py:119`, `backend/apps/pipeline/services/ranker.py:577-668`
- Manual review and apply flow is live: `backend/apps/suggestions/views.py:115-271`
- `FR-036` is implemented even though the docs still mark it pending:
  - backend coverage-gap endpoint: `backend/apps/graph/views.py:628-777`
  - tests: `backend/apps/graph/tests.py:288-382`
  - frontend copy/UI evidence: `frontend/src/app/graph/graph.component.html:1027`

### Code-verified partial

- `FR-034` is partially implemented, not absent:
  - topology edges already expose anchor/context data: `backend/apps/graph/views.py:471-490`
  - tests already assert the anchor field: `backend/apps/graph/tests.py:271-278`
  - crawler UI already renders anchor text and context class: `frontend/src/app/crawler/crawler.component.html:276-285`
  - but the spec also calls for a fuller audit experience, including anchor-frequency warning/reporting behavior: `docs/specs/fr034-link-context-quality-audit.md:15-24`
- `FR-037` is still partial:
  - backend leakage summary endpoint exists: `backend/apps/audit/views.py:56-112`
  - the spec calls for a richer leakage-map visualization and graph interaction layer: `docs/specs/fr037-silo-connectivity-leakage-map.md:17-25`
  - I did not find a matching frontend leakage-map implementation during repo search.

### Code-verified pending or seeded-only

- `FR-020` still appears genuinely pending:
  - backlog entry remains open: `FEATURE-REQUESTS.md:805-860`
  - readiness matrix still lists it as postponed: `backend/apps/diagnostics/health.py:1442-1463`
  - repo search found specs and wording, but no actual model-registry / hot-swap implementation.
- `FR-040`, `FR-042`, and `FR-044` are seeded, but not integrated:
  - `ContentItem` fields now exist: `backend/apps/content/models.py:249-274`
  - forward-declared recommended settings exist: `backend/apps/suggestions/recommended_weights_forward_settings.py:36-90`
  - tooltip/preset metadata exists in Angular settings TS: `frontend/src/app/settings/settings.component.ts:1041-1185`
  - diagnostics entries are still commented out: `backend/apps/diagnostics/signal_registry.py:238-276`
  - current pipeline/value-model search still does not show active scoring functions for these FRs.

## Status-Drift Findings

### 1. The docs undercount shipped functionality

`AI-CONTEXT.md` still lists `FR-036` inside pending FRs (`AI-CONTEXT.md:254-260`), but the code already ships a working implementation (`backend/apps/graph/views.py:628-777`, `backend/apps/graph/tests.py:288-382`).

Practical impact:
- a future engineer could waste time re-planning or duplicating `FR-036`;
- the status dashboard is stale by at least one FR.

### 2. The partial-note for FR-040 / FR-042 / FR-044 is now imprecise

The continuity file says these items are partial because config keys exist but the score fields are missing (`AI-CONTEXT.md:250-252`). That is no longer true: the score fields now exist on `ContentItem` (`backend/apps/content/models.py:249-274`).

The real current state is:
- fields exist;
- forward settings exist;
- diagnostics placeholders exist;
- scoring integration is still missing.

### 3. FR-034 is more implemented than the dashboard text suggests

The continuity note says `FR-034` only has parser/context refs and no usable UI (`AI-CONTEXT.md:247-249`). In practice, anchor/context evidence is already exposed in topology data and surfaced in the crawler table (`backend/apps/graph/views.py:471-490`, `frontend/src/app/crawler/crawler.component.html:276-285`).

The better classification is "partial with operator-visible subset already shipped," not "just refs exist."

## Current Business-Logic Flaws And Research-Backed Improvements

### 1. Import coverage is still artificially capped at five pages per source

Evidence:
- XenForo thread import loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:31-37`
- XenForo resource import loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:89-95`
- WordPress import loop: `services/http-worker/src/HttpWorker.Services/PipelineServices.cs:144-154`

Why this is a business-logic flaw:
- The system's downstream quality depends on having a representative corpus.
- A fixed `page <= 5` cap silently truncates larger forums and blogs.
- That under-import then propagates into embeddings, graph structure, PageRank, freshness, orphan detection, and suggestion generation.

Improve it by:
- replacing the fixed page cap with a continuation-token or resumable frontier loop;
- persisting per-scope crawl checkpoints so imports resume instead of restarting from page 1;
- prioritizing higher-value or fresher scopes first rather than stopping at an arbitrary depth.

Research basis:
- Cho, Garcia-Molina, and Page, ["Efficient Crawling Through URL Ordering"](https://archives.iw3c2.org/www7/proceedings/1919/com1919.htm) (1998)

### 2. Feedback reranking uses a daily presentation count, not real propensities

Evidence:
- rerank stats are aggregated only at the `(host_scope, destination_scope)` level: `backend/apps/pipeline/services/feedback_rerank.py:51-120`
- the exploit term uses `reviewed / exposure` where exposure is just presented-count or generated-count: `backend/apps/pipeline/services/feedback_rerank.py:108-161`
- presentation logging stores only `(suggestion, user, presented_date)`: `backend/apps/suggestions/models.py:726-759`

Why this is a business-logic flaw:
- The current model knows that a suggestion was shown on a day, but not:
  - rank position,
  - whether it was actually visible on screen,
  - how long it stayed visible,
  - which competing suggestions surrounded it.
- That means the reranker still learns from a weak proxy for exposure, not from true viewing propensity.
- The code comments describe inverse-propensity logic, but the stored signal is too coarse to support strong debiasing claims.

Improve it by:
- logging per-impression rank position and visibility state;
- storing enough impression detail to estimate propensities per displayed suggestion, not just per scope pair per day;
- moving from the current proxy correction toward propensity-weighted or doubly robust learning-to-rank.

Research basis:
- Joachims, Swaminathan, and Schnabel, ["Unbiased Learning-to-Rank with Biased Feedback"](https://www.ijcai.org/proceedings/2018/738) (2017)

### 3. Attribution currently mixes matched-control logic in Django with global-trend logic in the C# result shown to operators

Evidence:
- Django builds a matched control pool from same-silo, same-content-type pages and scores candidates on pre-period metrics: `backend/apps/analytics/impact_engine.py:31-123`
- Django then computes normalized deltas from the matched controls and stores `ImpactReport` quality fields such as `control_match_quality` and `is_conclusive`: `backend/apps/analytics/impact_engine.py:233-342`
- the C# worker instead uses a sitewide CTR trend multiplier as the counterfactual: `services/http-worker/src/HttpWorker.Services/GSCAttributionService.cs:31-100`
- the operator-facing search-impact list is driven from `GSCImpactSnapshot`, not `ImpactReport`: `backend/apps/analytics/views.py:1940-1959`
- the analytics UI explicitly describes the method as a "Global Control Baseline": `frontend/src/app/analytics/analytics.component.html:599-610`

Why this is a business-logic flaw:
- There are effectively two attribution stories in the codebase:
  - matched controls in Django;
  - global trend normalization in the C# output shown in the UI.
- That split can confuse operators and make the same suggestion look more or less trustworthy depending on which layer they inspect.
- The global baseline is also much coarser than the matched-control layer, so surfacing only that result throws away higher-quality counterfactual work already present elsewhere.

Improve it by:
- picking one primary operator-facing attribution contract and making both layers agree on it;
- preferring matched or synthetic controls over sitewide CTR when page-level controls are available;
- surfacing control quality and uncertainty alongside any uplift label shown in the UI.

Research basis:
- Brodersen et al., ["Inferring causal impact using Bayesian structural time-series models"](https://research.google.com/pubs/pub41854.html?trk=article-ssr-frontend-pulse_x-social-details_comments-action_comment-text) (2015)
- Abadie, Diamond, and Hainmueller, ["Synthetic Control Methods for Comparative Case Studies"](https://econpapers.repec.org/paper/nbrnberte/0335.htm) (2007/2010)

### 4. FR-018 auto-tuning still optimizes four global aggregate metrics instead of ranking quality

Evidence:
- the collector reduces the whole window to four aggregate signals: `services/http-worker/src/HttpWorker.Services/Analytics/WeightTunerDataCollector.cs:28-59`
- the contract only carries those four top-level metrics plus an applied-count indicator: `services/http-worker/src/HttpWorker.Core/Contracts/V1/WeightTuningContracts.cs:18-34`
- the optimizer score is a direct weighted sum of those metrics: `services/http-worker/src/HttpWorker.Services/Analytics/WeightObjectiveFunction.cs:44-50`

Why this is a business-logic flaw:
- Ranking quality is about ordering candidates correctly within each decision context.
- A single global blend of `GscLift`, `Ga4Ctr`, `ReviewApprovalRate`, and `MatomoClickRate` does not measure that.
- The current objective can improve the aggregate scalar while still making per-destination ranking worse.

Improve it by:
- evaluating candidate weights against per-destination ranking outcomes, not only global averages;
- using ranking-aware objectives such as NDCG, approval-at-top-k, applied-at-top-k, or counterfactual listwise loss;
- keeping the current bounded optimizer if desired, but feeding it a ranking-aware objective instead of a metric blend.

Research basis:
- Cao et al., ["Learning to Rank: From Pairwise Approach to Listwise Approach"](https://dl.acm.org/doi/10.1145/1273496.1273513) (2007)
- Joachims, Swaminathan, and Schnabel, ["Unbiased Learning-to-Rank with Biased Feedback"](https://www.ijcai.org/proceedings/2018/738) (2017)

## Not A Current Flaw Anymore

The previous version of this audit said the value model still duplicated traffic and engagement and still used max-normalized Jaccard. That is no longer true in the current code:

- co-occurrence now uses sigmoid-normalized log-likelihood ratio rather than site-max Jaccard normalization: `backend/apps/cooccurrence/services.py:336-383`
- traffic and engagement are now separate destination fields in the value model: `backend/apps/cooccurrence/services.py:548-566`

That does not prove the value model is perfect, but it does mean the earlier criticism should not remain in the active flaw list.

## Priority Order

If this were my next-work queue, I would do it in this order:

1. Fix import coverage and checkpointing.
2. Unify attribution around one counterfactual contract and expose control quality clearly.
3. Strengthen feedback-impression logging so the reranker can estimate real propensities.
4. Replace the FR-018 objective with ranking-aware evaluation.
5. Reconcile `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` with the current code state.

## Bottom Line

The repo already contains a large amount of real product logic. The biggest risks are no longer "missing scaffolding" problems. They are silent logic-quality problems: incomplete imports, weak exposure modeling, split attribution semantics, and an optimizer that still tunes toward a convenient summary metric instead of the ranking task itself.
