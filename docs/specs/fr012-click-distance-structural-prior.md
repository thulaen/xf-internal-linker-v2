# FR-012 - Click-Distance Structural Prior

## Confirmation

Simple version first.

- Active target confirmed: `Phase 15 / FR-012 - Click-Distance Structural Prior` is the next queued roadmap item in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Doc gap confirmed: this spec file was missing, even though earlier shipped FRs already have detailed source-of-truth spec docs under `docs/specs/`.
- Repo confirmed: the live branch already has separate FR-006 weighted authority, FR-007 link freshness, FR-008 phrase relevance, FR-009 learned-anchor corroboration, FR-010 rare-term propagation, and FR-011 field-aware relevance.
- Repo confirmed: there is no current FR-012 click-distance score, settings API, diagnostics block, or implementation in this branch today.

## Current Repo Map

### Structural data already available

- `backend/apps/content/models.py`
  - `ContentItem.scope`
  - `ContentItem.url`
  - `ScopeItem.parent`
  - `ScopeItem.title`
  - `ScopeItem.scope_type`
- `backend/apps/pipeline/services/pipeline.py`
  - already loads destination and host `ContentRecord` rows.
  - already includes scope, parent, and grandparent identity for ranking-time structure-aware features.
- `backend/apps/pipeline/services/ranker.py`
  - already has additive ranking hooks for newer FR layers.
  - already uses bounded per-feature score components.

### Structural data that is not available

- The repo does **not** store a full site-navigation graph.
- The repo does **not** store homepage-to-page click paths.
- The repo does **not** store menu, breadcrumb, or sidebar traversal links.
- The repo does **not** store a dedicated content-level shortest-path graph for FR-012 today.

### Existing storage and UI patterns already available

- `backend/apps/content/models.py`
  - already stores destination-level numeric feature fields such as:
    - `march_2026_pagerank_score`
    - `link_freshness_score`
- `backend/apps/suggestions/models.py`
  - already stores separate suggestion-level score fields and diagnostics JSON for newer ranking layers.
- `backend/apps/core/views.py`
  - already exposes per-feature settings APIs and validation helpers.
- `backend/apps/suggestions/views.py`
  - already snapshots per-feature settings and algorithm versions into `PipelineRun.config_snapshot`.
- `frontend/src/app/review/suggestion.service.ts`
  - already models separate review-detail score and diagnostics blocks.
- `frontend/src/app/settings/settings.component.html`
  - already exposes separate settings cards for newer ranking layers.

## Plain-English Summary

Simple version first.

Some pages sit near the top of the site structure.
Some pages are buried deeper.

FR-012 adds a small structure hint:

- pages that are fewer clicks away from a chosen structural root get a higher score;
- pages that are deeper get a lower score;
- the effect stays soft, bounded, and explainable;
- it never replaces the real ranking signals.

This is not saying "always link to shallow pages."
It only says "all else being equal, shallower pages may deserve a small nudge."

## Problem Summary

Right now the ranker understands:

- semantic similarity;
- keyword overlap;
- node affinity;
- host quality;
- FR-006 authority;
- FR-007 freshness;
- FR-008 phrase evidence;
- FR-009 learned anchors;
- FR-010 propagated rare terms;
- FR-011 field-aware relevance.

What it still does **not** understand is simple structural accessibility.

Example:

- Page A and Page B may both match the host sentence well.
- Page A may sit one structural step below a root category.
- Page B may sit five structural steps deep.
- The current ranker has no dedicated FR-012 way to express that difference.

FR-012 fills that gap with a small, separate structural prior.

## Goal

Add a separate FR-012 destination-side score that:

- represents a soft click-distance prior;
- is computed from a safe structural shortest-path model the repo can really support;
- stays bounded in `0..1`;
- stays neutral when the path cannot be computed safely;
- is stored separately from FR-006 authority;
- is converted into a centered additive ranker component;
- has its own settings, diagnostics, snapshot wiring, and review exposure.

## Non-Goals

FR-012 does not:

- replace semantic or keyword relevance;
- replace FR-006 authority;
- replace FR-007 freshness;
- replace FR-008 phrase matching;
- replace FR-009 learned-anchor corroboration;
- replace FR-010 rare-term propagation;
- replace FR-011 field-aware relevance;
- create a full crawler-derived click graph;
- infer real user clickstream behavior;
- add analytics-driven navigation weights;
- redesign the site's actual URL structure;
- implement later reranking phases such as FR-013 through FR-015.

## Source Summary

Primary source actually read:

- [US8082246B2 - Search result scoring using click distance and URL depth style signals](https://patents.google.com/patent/US8082246B2/en)

Useful source ideas:

- structural distance can be used as a ranking prior;
- that distance should be softened, not used as a hard cutoff;
- a saturation constant should stop close-vs-deep differences from exploding;
- URL depth can be used as a supporting structural signal when needed.

Useful supporting public text:

- [Justia text mirror for the same family / formula discussion](https://patents.justia.com/patent/20070038622)

Repo-safe reading of the source:

- the patent assumes a broader search/index setting than this app has;
- this repo is not a whole-web search engine;
- the reusable idea is still valid:
  - compute a structural depth,
  - blend in URL depth if helpful,
  - apply a bounded saturation formula,
  - use the result as one small ranking signal.

## Math-Fidelity Note

### Directly supported by the source

- use click distance or shortest-path depth as a ranking prior;
- combine structural depth with URL-depth style information;
- use a bounded saturation formula rather than a linear penalty;
- keep the signal as part of ranking, not the whole ranking system.

### Adapted for this repo

- Inference: the repo's scope tree is the safest structural graph available in v1.
- Inference: `ScopeItem.parent` is the real shortest-path backbone the app can trust today.
- Inference: `ContentItem.url` path depth is a useful smoothing term, not the primary path signal.
- Inference: the stored score should live on `ContentItem`, because the structural prior is destination-side and independent of the chosen host sentence.

### Deliberately not carried over in FR-012 v1

- no homepage crawl graph;
- no menu-link graph;
- no content-link graph as the FR-012 root path source;
- no user-behavior clickstream;
- no learned structural priors;
- no source-type-specific formula variants in v1.

## Hard Scope Boundary

FR-012 must stay separate from:

- `FR-006`
  - authority measures how editorially central a destination is in the existing-link graph.
  - FR-012 measures how structurally shallow or deep the destination is in the site tree.
- `FR-007`
  - freshness measures timing and growth of inbound links.
  - FR-012 measures structural path depth only.
- `FR-008`
  - phrase matching is sentence-to-destination text evidence.
  - FR-012 is destination-side structure only.
- `FR-009`
  - learned anchors are vocabulary evidence from existing anchor text.
  - FR-012 is not text evidence.
- `FR-010`
  - rare-term propagation borrows topical evidence from related pages.
  - FR-012 does not borrow text from anywhere.
- `FR-011`
  - field-aware relevance scores destination text fields.
  - FR-012 does not score text fields at all.

Hard rule:

- FR-012 v1 is a separate structural prior only.

## Structural Model Used In This Repo

Simple version first.

The repo does not know the real click path from the homepage.
So FR-012 must define a safe substitute that the code can really compute.

### Root model

For FR-012 v1:

- each top-level `ScopeItem` with `parent is null` acts as a structural root;
- each destination inherits the root of its own scope tree;
- the root is stored only in diagnostics in v1, not as a permanent model field.

### Shortest-path model

For FR-012 v1:

- shortest-path depth is the number of parent hops from the destination's `scope` up to its root scope;
- this is the structural path length the repo can compute safely and deterministically today.

### Why not use the content-link graph

Because that would drift into FR-006 territory.

- FR-006 already owns the existing-link graph.
- FR-012 is supposed to capture navigational or structural shallowness.
- The scope tree is the closest repo-safe stand-in for that idea.

### Why include URL depth

Because the patent family also uses URL-depth-like structure signals, and the repo already stores `ContentItem.url`.

But in this app:

- URL depth is only a helper term;
- structural scope depth remains the main signal.

## Scoring Formula

### Inputs

For one destination:

- `scope_depth`
  - number of parent hops from the destination scope to its root scope.
- `structural_click_distance`
  - `scope_depth + 1`
  - this keeps the root-level case from acting like a zero-distance singularity.
- `url_depth`
  - count of non-empty path segments in `ContentItem.url`.
- `k_cd`
  - saturation constant.
- `b_cd`
  - structural depth weight.
- `b_ud`
  - URL depth weight.

### Blended depth

Use:

```text
blended_depth = ((b_cd * structural_click_distance) + (b_ud * url_depth)) / (b_cd + b_ud)
```

Guardrail:

- if `b_cd + b_ud <= 0`, FR-012 must go neutral rather than score unsafely.

### Final stored score

Use:

```text
click_distance_score = k_cd / (k_cd + blended_depth)
```

Then clamp to `0..1`.

### Ranker component

Use the same centered pattern as other newer ranking layers:

```text
score_click_distance_component = 2 * (click_distance_score - 0.5)
```

Then add:

```text
ranking_weight * score_click_distance_component
```

to the final additive ranker score.

## Neutral Fallback Rules

FR-012 must return neutral `0.5` when:

- the destination has no scope;
- the destination scope cannot be connected safely to a root;
- the scope tree has a cycle or broken parent chain;
- settings are invalid for safe scoring;
- the destination row itself is missing during live diagnostics.

Neutral states should be explicit, not hidden.

## Operator Settings

FR-012 v1 should expose exactly these settings:

- `ranking_weight`
  - default `0.0`
  - bounded small so the signal stays soft
- `k_cd`
  - default `4.0`
  - saturation constant
- `b_cd`
  - default `0.75`
  - structural depth weight
- `b_ud`
  - default `0.25`
  - URL depth weight

### Validation rules

- `ranking_weight` must be between `0.0` and `0.10`
- `k_cd` must be between `0.5` and `12.0`
- `b_cd` must be between `0.0` and `1.0`
- `b_ud` must be between `0.0` and `1.0`
- `b_cd + b_ud` must be greater than `0`

## Data Storage

### Destination-level storage

Add to `ContentItem`:

- `click_distance_score: FloatField`
  - default `0.5`
  - indexed

Reason:

- the structural prior belongs to the destination itself;
- it should not be recomputed separately for every host sentence during one pipeline run.

### Suggestion-level storage

Add to `Suggestion`:

- `score_click_distance: FloatField`
  - denormalized copy of the destination's stored FR-012 score at suggestion time
- `click_distance_diagnostics: JSONField`
  - suggestion-time diagnostic snapshot

Reason:

- review and audit should show what score the suggestion actually used at the time it was created.

## Diagnostics Shape

FR-012 diagnostics should be plain and explainable.

Expected fields:

- `click_distance_score`
- `click_distance_data_state`
- `root_scope_id`
- `root_scope_title`
- `structural_click_distance`
- `url_depth`
- `blended_depth`
- `scope_depth`
- `k_cd`
- `b_cd`
- `b_ud`

### Expected states

- `computed`
- `neutral_missing_scope_path`
- `neutral_invalid_settings`
- `neutral_missing_content`

## Pipeline Wiring

### Recalculation path

FR-012 needs a dedicated recalculation path, like FR-006 and FR-007.

That path should:

- load all scopes;
- build a safe root/depth map;
- load all content items;
- compute one destination-side score per content item;
- persist the new score;
- report counts by data state.

### Pipeline-run use

When the suggestion pipeline runs:

- load the persisted destination `click_distance_score`;
- center it to a ranker component only if `ranking_weight > 0`;
- add it into the ranker separately from FR-006 to FR-011;
- store the destination-side score and diagnostics on `Suggestion`.

### Config snapshot

Add FR-012 settings into `PipelineRun.config_snapshot`:

- `click_distance`

Add FR-012 algorithm metadata into:

- `config_snapshot["algorithm_versions"]["click_distance"]`

## API Surface

FR-012 v1 should add:

- `GET /api/settings/click-distance/`
- `PUT /api/settings/click-distance/`
- `POST /api/settings/click-distance/recalculate/`

Content/detail payloads should expose:

- `click_distance_score`

Suggestion detail payloads should expose:

- `score_click_distance`
- `click_distance_diagnostics`
- live destination diagnostics if the review UI already follows that pattern

## Frontend Exposure

### Settings page

Add a separate card:

- title: `Click Distance`
- fields:
  - ranking weight
  - saturation constant (`k_cd`)
  - structural depth weight (`b_cd`)
  - URL depth weight (`b_ud`)
- actions:
  - save
  - recalculate

### Review detail

Add:

- one score row for `Click Distance`
- one plain-English summary block
- one small detail line that shows:
  - structural depth
  - URL depth
  - root scope
  - blended depth

### Content views

Add:

- `click_distance_score` to list/detail serializers
- content ordering support by `click_distance_score`

## Plain-English Review Language

The reviewer-facing summary should stay simple.

Good examples:

- "Computed from site structure."
- "Shallow pages get a small boost. Deep pages get a small penalty."
- "Neutral because the app could not find a safe structural path for this page."

Avoid:

- raw patent jargon;
- unexplained formula names;
- claiming the score is a real user clickstream metric.

## Test Plan

### Service tests

- shallower structural paths produce higher scores than deeper ones;
- larger `k_cd` flattens the penalty;
- invalid blend weights go neutral;
- missing scope path goes neutral;
- URL depth changes the score only as a supporting term.

### Persistence tests

- recalculation writes `click_distance_score` to `ContentItem`;
- recalculation resets untouched rows back to neutral before rewriting;
- diagnostics counters report computed vs neutral states.

### Ranker tests

- `ranking_weight = 0` keeps ranking unchanged;
- positive weight adds the centered FR-012 component;
- FR-012 does not override existing hard blocks.

### API tests

- settings endpoint returns defaults;
- settings round-trip persists values;
- invalid bounds are rejected;
- recalculate endpoint returns a job id.

### Serializer and review tests

- content endpoints expose `click_distance_score`;
- suggestion detail exposes `score_click_distance`;
- review detail exposes FR-012 diagnostics and plain-English labels.

### Migration check

- `makemigrations --check --dry-run` must report no drift after the FR-012 model fields are added.

## Implementation Notes For The AI

- Keep FR-012 separate from FR-006 authority math.
- Do not invent a fake navigation graph the repo does not store.
- Use the scope tree as the structural shortest-path model in v1.
- Treat URL depth as a smoothing term, not the main structural path.
- Keep neutral fallback at `0.5`.
- Keep ranking impact additive and off by default.
- Preserve the existing per-feature settings / snapshot / diagnostics patterns already used by FR-006 through FR-011.

## Recommended File Targets

- `docs/specs/fr012-click-distance-structural-prior.md`
- `backend/apps/content/models.py`
- `backend/apps/content/serializers.py`
- `backend/apps/content/views.py`
- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `backend/apps/pipeline/services/click_distance.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/tasks.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`
- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`

## Final Rule

Simple version first.

FR-012 is allowed to be helpful.
It is not allowed to be bossy.

That means:

- small weight;
- bounded score;
- neutral fallback when unsafe;
- clear diagnostics;
- separate from the rest of the ranker.
