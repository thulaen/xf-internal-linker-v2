# FR-006 - Weighted Link Graph / Reasonable Surfer Scoring

## Confirmation

- Active phase confirmed: `Phase 9 / FR-006 - Weighted Link Graph / Reasonable Surfer Scoring` is the exact next target in `AI-CONTEXT.md`.
- Backlog confirmed: `FR-006` is a real pending request in `FEATURE-REQUESTS.md`. It is not the `FR-016` template placeholder.
- Repo confirmed: no existing `March 2026 PageRank`, `weighted pagerank`, or `reasonable surfer` implementation is present in the codebase today.

## Current Repo Map

### Existing-link extraction and persistence

- `backend/apps/pipeline/services/link_parser.py`
  - Parses BBCode links, HTML anchors, and bare URLs.
  - Resolves internal targets and returns `LinkEdge`.
- `backend/apps/graph/services/graph_sync.py`
  - Reconciles parsed edges into `ExistingLink`.
- `backend/apps/graph/models.py`
  - Stores `ExistingLink(from_content_item, to_content_item, anchor_text, discovered_at)`.
- `backend/apps/pipeline/tasks.py`
  - Calls `extract_internal_links(...)`, `sync_existing_links(...)`, and `refresh_existing_links()` during import/sync.

### Graph or edge models and migrations

- `backend/apps/graph/models.py`
- `backend/apps/graph/migrations/0001_initial.py`
- `backend/apps/graph/admin.py`

### Authority or PageRank computation

- `backend/apps/pipeline/services/pagerank.py`
  - Loads `ExistingLink` into a sparse matrix.
  - Uses uniform outbound weights `1 / outdegree(source)`.
  - Persists into `ContentItem.march_2026_pagerank_score`.
- `backend/apps/pipeline/tasks.py`
  - Runs `run_pagerank()` after sync/import.
- `backend/apps/content/models.py`
  - Stores `march_2026_pagerank_score` on `ContentItem`.

### Ranking feature assembly

- `backend/apps/pipeline/services/pipeline.py`
  - Loads `ContentRecord`.
  - Calls `score_destination_matches(...)`.
  - Persists `Suggestion` records.
- `backend/apps/pipeline/services/ranker.py`
  - Current final score uses semantic + keyword + node affinity + quality + silo.
  - Current `score_quality` is based on the host page's normalized `march_2026_pagerank_score`.
  - Current destination `score_march_2026_pagerank` and `score_velocity` are persisted for review, but are not part of `score_final`.

### Diagnostics or explanations returned to review

- `backend/apps/suggestions/models.py`
  - `Suggestion` stores score breakdown fields.
  - `PipelineDiagnostic` stores skip reasons.
- `backend/apps/suggestions/serializers.py`
  - `SuggestionDetailSerializer` returns score fields to review.
- `backend/apps/suggestions/admin.py`
  - Django admin exposes suggestion score breakdown.
- `frontend/src/app/review/suggestion.service.ts`
  - Frontend `SuggestionDetail` type includes `score_march_2026_pagerank`.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - Review dialog shows score bars for semantic, keyword, node affinity, quality, PageRank, and velocity.

### Settings persistence and settings API

- `backend/apps/core/models.py`
  - `AppSetting` is the typed key/value settings store.
- `backend/apps/core/views.py`
  - Current settings APIs live here.
  - Current shipped endpoints are appearance, silos, and WordPress.
- `backend/apps/api/urls.py`
  - Wires `/api/settings/...` routes.
- `frontend/src/app/settings/silo-settings.service.ts`
  - Frontend service for current settings APIs.
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

### Serializers, admin, or UI that already expose authority-like values

- `backend/apps/content/models.py`
  - `ContentItem.march_2026_pagerank_score`
- `backend/apps/content/serializers.py`
  - Exposes `march_2026_pagerank_score` in content list/detail serializers.
- `backend/apps/content/views.py`
  - Allows ordering by `march_2026_pagerank_score`.
- `backend/apps/content/admin.py`
  - Shows `march_2026_pagerank_score` in Django admin.
- `backend/apps/suggestions/models.py`
  - `Suggestion.score_march_2026_pagerank`
- `backend/apps/suggestions/serializers.py`
  - Returns `score_march_2026_pagerank` in suggestion detail.
- `backend/apps/suggestions/admin.py`
  - Shows `score_march_2026_pagerank` in admin.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - Shows `PageRank` in review UI.

## Workflow Drift / Doc Mismatch Found During Inspection

- `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` correctly point to `Phase 9 / FR-006` as the next real target.
- Important code-vs-doc drift: the continuity docs say hybrid scoring includes PageRank + velocity, but live `backend/apps/pipeline/services/ranker.py` does not use destination PageRank or velocity in `score_final` today.
- `PipelineRun.config_snapshot` exists in `backend/apps/suggestions/models.py`, but `backend/apps/suggestions/views.py` does not populate it when a run starts.
- `backend/apps/pipeline/services/link_parser.py` does not preserve true mixed-syntax link order today. It collects BBCode matches, then HTML matches, then bare URLs. That is fine for plain existence checks, but it is not safe for position-based weighting.
- `backend/apps/graph/services/graph_sync.py` currently creates and deletes edges, but does not update non-key edge fields for edges that still exist. FR-006 needs update-in-place behavior because edge features can change without the source/destination pair changing.

## Source Summary

### Source documents actually read

- [US7716225B1](https://patents.google.com/patent/US7716225B1/en)
- [US6285999B1](https://patents.google.com/patent/US6285999B1/en)
- [Brin and Page, "The Anatomy of a Large-Scale Hypertextual Web Search Engine" (1998)](https://snap.stanford.edu/class/cs224w-readings/Brin98Anatomy.pdf)

### Concepts used from the sources

- From `US7716225B1`:
  - a link can be assigned a weight tied to the probability that a user would choose it;
  - the weight can depend on link features, source-document features, and target-document features;
  - example feature families include link position, visual prominence, source link count, document type, and surrounding text.
- From `US6285999B1` and Brin/Page:
  - PageRank is a probability distribution over pages;
  - it is computed from a normalized link matrix by iterative power updates;
  - the random-surfer view is the right baseline mental model;
  - uniform outbound probability is the current standard case.

### What was clear

- A weighted link graph is meant to bias transitions by link-follow likelihood.
- The feature is separate from standard PageRank, not a replacement for it.
- Position and prominence are squarely inside scope for a reasonable-surfer style graph.

### What remained ambiguous

- `US7716225B1` describes weights as link-selection probabilities, but the patent's equation is written as a weight multiplied into the classic `1/outdegree` form.
- The patent allows a learned weighting model, but this repo has no click logs, no rendered DOM/CSS feature pipeline, and no user-behavior training data.
- The patent mentions source update frequency and surrounding-text topical relevance, but using those directly here would collide with later planned phases for freshness and phrase/field relevance.

## Math-Fidelity Note

### Directly supported by the sources

- Use the existing directed link graph.
- Assign per-edge weights that represent relative follow-likelihood.
- Run a PageRank-style iteration over those weighted edges.
- Keep standard `march_2026_pagerank_score` as-is.

### Adapted for this repo

- No learned model is used.
  - Reason: this repo has no primary behavior data to train one safely.
- No font/color/rendered-DOM features are used.
  - Reason: the current extractor only sees BBCode/HTML strings, not computed layout.
- No freshness, update-frequency, phrase matching, field weighting, siloing, click-distance, reranking, clustering, or diversity features are used.
  - Reason: those belong to later phases or existing separate logic.
- Raw edge scores are normalized per source page into outbound probabilities before iteration.
  - Reason: this preserves a valid probability distribution, gives exact uniform-weight parity with today's `pagerank.py`, and is the narrowest low-regression interpretation of the patent.

### Alternatives considered

1. Patent-literal raw multiplier: `w_ij / outdegree(i)`
2. Per-source normalized transition probability: `P(i->j) = s_ij / sum_k s_ik`
3. Learned click-choice model

### Chosen interpretation

- Choose option 2.
- Treat persisted edge features as inputs to a positive raw score `s_ij`.
- Normalize `s_ij` across each source page's outgoing links to get the weighted transition matrix.
- This is the safest interpretation because:
  - it stays faithful to the "probability a user selects the link" language;
  - it preserves PageRank mass conservation;
  - it converges in the same sparse-matrix shape as the current implementation;
  - it falls back exactly to current PageRank when all outgoing links from every source have equal raw score.

## Problem Definition

Simple version first.

Right now every outgoing internal link from a page counts the same. FR-006 adds a second authority score where links that look more like real editorial links count more, and links that look more like boilerplate count less.

Technical definition:

- compute a new destination metric called `march_2026_pagerank_score`;
- base it on the same `ContentItem` node set and `ExistingLink` edge set used by the weighted-link graph;
- persist stable edge features needed to derive reasonable-surfer weights;
- replace the old `pagerank_score` field with `march_2026_pagerank_score`;
- expose enough settings and review data to inspect March 2026 PageRank safely;
- keep ranking impact opt-in by default to avoid silent regressions.

## Chosen Weighted-Link Interpretation

### Non-goals and phase boundary

FR-006 must stay separate from:

- freshness or growth signals (`FR-007`)
- phrase-based destination/context relevance (`FR-008`)
- learned anchor vocabulary (`FR-009`)
- field weighting (`FR-011`)
- structural click-distance priors (`FR-012`)
- reranking, clustering, and diversity (`FR-013` to `FR-015`)
- current silo logic (`FR-005`)

### Edge identity and dedup policy

- Weighted authority uses one logical edge per `source -> destination`.
- If a source links to the same destination more than once, keep the earliest resolved occurrence in true document order as the weighted representative edge.
- Keep current `ExistingLink` storage as the edge table, but the weighted graph loader must defensively coalesce accidental duplicate rows by `from_content_item` + `to_content_item` if any exist.

### Persisted edge features

Extend `ExistingLink` with these stable, extraction-time fields:

- `extraction_method`
  - choices: `bbcode_anchor`, `html_anchor`, `bare_url`
- `link_ordinal`
  - zero-based order of this resolved internal link inside the source content, after sorting in true document order
- `source_internal_link_count`
  - total number of resolved internal links on the source content after dedup policy
- `context_class`
  - choices: `contextual`, `weak_context`, `isolated`

Existing persisted field reused directly:

- `anchor_text`
  - already stored today
  - blank means "no visible anchor text was captured"

### Edge feature definitions

- `extraction_method`
  - `bbcode_anchor`: link came from `[URL=...]anchor[/URL]`
  - `html_anchor`: link came from `<a href="...">anchor</a>`
  - `bare_url`: link came from a plain naked URL in text
- `link_ordinal`
  - computed from ordered match spans, not regex-family order
- `source_internal_link_count`
  - count of resolved internal links on the source content after same-destination dedup
- `context_class`
  - `contextual`: stripped local text window has normal prose tokens on both sides of the link
  - `weak_context`: prose tokens appear on only one side
  - `isolated`: no prose tokens on either side, or the link appears standalone/list-like

### Chosen raw edge scoring function

Let `anchor_blank(e)` be true when `anchor_text.strip()` is empty.

Let:

- `kind_factor(e)` =
  - `bare_url_factor` if `extraction_method == "bare_url"`
  - `empty_anchor_factor` if `anchor_blank(e)` is true for a non-bare anchor
  - `1.0` otherwise

- `position_ratio(e)` =
  - `0.0` if `source_internal_link_count <= 1`
  - otherwise `link_ordinal / (source_internal_link_count - 1)`

- `position_factor(e)` =
  - `1.0 - position_bias * position_ratio(e)`

- `context_factor(e)` =
  - `1.0` for `contextual`
  - `weak_context_factor` for `weak_context`
  - `isolated_context_factor` for `isolated`
  - `1.0` if the feature is missing

Raw edge score:

`raw_edge_score(e) = max(1e-6, kind_factor(e) * position_factor(e) * context_factor(e))`

Notes:

- This is intentionally small and conservative.
- It uses only features that are both source-backed in spirit and realistically extractable in this repo.
- `source_internal_link_count` is used only to derive relative position.
  - It is not used as its own multiplicative factor because any source-constant factor would cancel during per-source normalization.

### Outbound normalization method

For each source node `i` with active outgoing edges to non-deleted destinations:

- compute `raw_edge_score(i, j)` for every outgoing edge;
- if all scores are finite and the row sum is greater than zero:
  - `P_w(i -> j) = raw_edge_score(i, j) / sum_k raw_edge_score(i, k)`
- otherwise:
  - fallback to uniform weighting: `P_w(i -> j) = 1 / outdegree(i)`

This normalization is required.

It gives two good properties:

- the outbound probabilities from each source sum to `1`;
- if every outgoing edge on a source page has equal raw score, the weighted graph collapses back to standard PageRank behavior for that source.

### Missing-feature handling

- missing `context_class` => use neutral `context_factor = 1.0`
- missing `link_ordinal` or `source_internal_link_count` => treat like a single-link page, so `position_factor = 1.0`
- blank `anchor_text`
  - bare URL => `bare_url_factor`
  - non-bare anchor with blank text => `empty_anchor_factor`
- malformed or non-finite raw score => ignore that row's feature weighting and fallback that source row to uniform outbound probability
- source with no outgoing edges => treat as dangling exactly like current `pagerank.py`

### Weighted authority iteration

Use the same damping semantics and convergence strategy as the current `backend/apps/pipeline/services/pagerank.py`.

Definitions:

- `teleport = 0.15`
- `max_iter = 100`
- `tolerance = 1e-6`

Iteration:

- `link_mass = P_w @ ranks`
- `dangling_mass = sum(ranks[source] for dangling sources)`
- `next_ranks = (1 - teleport) * link_mass`
- `next_ranks += ((1 - teleport) * dangling_mass + teleport) / N`
- renormalize so `sum(next_ranks) == 1`
- stop when L1 delta is below `tolerance`, or after `max_iter`

Persist result into `ContentItem.march_2026_pagerank_score`.

Deleted content handling:

- same as current PageRank
- non-deleted content participates
- deleted content gets reset to `0.0`

## Stored Fields Required

### ExistingLink

Add fields to `backend/apps/graph/models.py`:

- `extraction_method: CharField`
- `link_ordinal: PositiveIntegerField(null=True, blank=True)`
- `source_internal_link_count: PositiveIntegerField(null=True, blank=True)`
- `context_class: CharField`

Recommended indexes:

- `Index(fields=["from_content_item", "link_ordinal"])`
- keep current `from_content_item` and `to_content_item` indexes

### ContentItem

Add field to `backend/apps/content/models.py`:

- `march_2026_pagerank_score: FloatField(default=0.0, db_index=True)`

Recommended index:

- `Index(fields=["content_type", "march_2026_pagerank_score"])`

### Suggestion

Add field to `backend/apps/suggestions/models.py`:

- `score_march_2026_pagerank: FloatField(default=0.0)`

Reason:

- review needs to compare standard vs weighted destination authority side by side;
- this mirrors the existing `score_march_2026_pagerank` pattern;
- it does not require a larger explanation-model rewrite in this phase.

## Settings, Defaults, Bounds, and Validation

### Settings storage

Persist through `AppSetting` in category `ml`.

Keys:

- `weighted_authority.ranking_weight`
- `weighted_authority.position_bias`
- `weighted_authority.empty_anchor_factor`
- `weighted_authority.bare_url_factor`
- `weighted_authority.weak_context_factor`
- `weighted_authority.isolated_context_factor`

### Defaults

- `ranking_weight = 0.0`
- `position_bias = 0.5`
- `empty_anchor_factor = 0.6`
- `bare_url_factor = 0.35`
- `weak_context_factor = 0.75`
- `isolated_context_factor = 0.45`

### Bounds

- `0.0 <= ranking_weight <= 0.25`
- `0.0 <= position_bias <= 1.0`
- `0.1 <= empty_anchor_factor <= 1.0`
- `0.1 <= bare_url_factor <= 1.0`
- `0.1 <= weak_context_factor <= 1.0`
- `0.1 <= isolated_context_factor <= 1.0`

### Validation rules

- every numeric setting must be finite
- context and kind factors must be positive
- `isolated_context_factor <= weak_context_factor <= 1.0`
- `bare_url_factor <= 1.0`
- saving settings does not change `march_2026_pagerank_score`
- changed settings only affect `march_2026_pagerank_score` after a March 2026 PageRank recalculation or the next full graph refresh/import cycle

## Ranking Feature Assembly

### Current-state constraint

Do not rewrite current `score_quality`, velocity handling, or destination PageRank handling as part of FR-006.

That would mix FR-006 with other backlog cleanup.

### Chosen ranking behavior

- Always compute and persist `march_2026_pagerank_score`.
- Keep standard `march_2026_pagerank_score` untouched and still exposed everywhere it already appears.
- Add `march_2026_pagerank_score` as a new optional destination-level ranking signal.
- Gate its effect with `weighted_authority.ranking_weight`, default `0.0`.

### Exact ranker behavior

In `backend/apps/pipeline/services/pipeline.py` and `backend/apps/pipeline/services/ranker.py`:

- load `march_2026_pagerank_score` into `ContentRecord`
- derive global min/max bounds for `march_2026_pagerank_score`
- normalize it with the same log-minmax style already used for PageRank-derived quality signals
- compute:
  - `score_march_2026_pagerank_component = normalized(destination.march_2026_pagerank_score)`
- add to final score:
  - `score_final += ranking_weight * score_march_2026_pagerank_component`

Persist on `Suggestion`:

- `score_march_2026_pagerank = destination.march_2026_pagerank_score`

Important:

- `score_march_2026_pagerank` is for review and admin display
- the normalized internal component does not need its own stored DB field in FR-006

Reason:

- this keeps the schema and UI change small;
- the review surface can still compare standard vs March 2026 PageRank directly;
- ranking impact remains opt-in and bounded.

## Diagnostics to Expose

### Review detail

Extend `SuggestionDetailSerializer` and the Angular review dialog to show:

- `score_march_2026_pagerank`

Display label recommendation:

- `March 2026 PageRank`

### Content APIs and admin

Expose `march_2026_pagerank_score` in:

- content list/detail serializers
- content admin list/detail
- suggestion admin score breakdown

### Edge inspection

Expose edge weighting features in `ExistingLinkAdmin`:

- `extraction_method`
- `link_ordinal`
- `source_internal_link_count`
- `context_class`

No new public ExistingLink API is required in FR-006.

### Run/config comparison

For reproducibility, FR-006 should begin using `PipelineRun.config_snapshot` for the FR-006 settings when a pipeline run starts.

Minimum snapshot payload addition:

- the six `weighted_authority.*` settings values

Reason:

- the field already exists;
- FR-006 explicitly asks for tuning and comparison;
- without a snapshot, later review cannot tell which March 2026 PageRank settings produced a run.

## API, Admin, Review, and UI Impact

### Backend API

Add:

- `GET /api/settings/weighted-authority/`
- `PUT /api/settings/weighted-authority/`
- `POST /api/settings/weighted-authority/recalculate/`

Recalculate endpoint behavior:

- dispatch a Celery task that recomputes `march_2026_pagerank_score` from the current graph and current FR-006 settings
- return `202` with a `job_id`
- do not force a full content resync

### Admin

Likely touched:

- `backend/apps/content/admin.py`
- `backend/apps/graph/admin.py`
- `backend/apps/suggestions/admin.py`

### Review UI

Likely touched:

- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`

Required change:

- add one new review row for `March 2026 PageRank`

### Settings UI

Likely touched:

- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Required controls:

- numeric fields for the six FR-006 settings
- save action
- separate `Recalculate March 2026 PageRank` action
- short helper text saying the app now uses this as its authority score

### Out of scope UI work

- no full `/graph` visualization work in FR-006
- no new diagnostics dashboard screen in FR-006

## Fallback Behavior When Disabled or Incomplete

- Standard `march_2026_pagerank_score` keeps computing exactly as it does today.
- If `ranking_weight == 0.0`, suggestion ranking stays unchanged even though March 2026 PageRank is computed and stored.
- If FR-006 settings are saved but recalculation has not run yet, old `march_2026_pagerank_score` values remain in place until recalculated.
- If graph rows still have legacy null FR-006 edge features, weighted computation uses neutral fallbacks and still produces a valid matrix.
- If a whole source row cannot produce valid weighted features, that source row falls back to uniform outbound probability.

## Regression Risks and Concrete Mitigations

### 1. Wrong link order because current extractor is not ordered across syntax families

Mitigation:

- replace `_find_urls()` with ordered match-span extraction
- sort all candidate matches by source offset before dedup and feature assignment
- add mixed BBCode + HTML + bare URL tests

### 2. Edge features go stale because current graph sync does not update retained rows

Mitigation:

- update `sync_existing_links(...)` so it bulk-updates changed FR-006 feature fields on edges that still exist
- do not rely on create/delete only

### 3. Settings changes create stale derived scores

Mitigation:

- persist only stable extraction features on edges
- do not persist settings-dependent normalized probabilities on edges
- provide a dedicated recalculation task for `march_2026_pagerank_score`

### 4. Scope creep into later phases

Mitigation:

- do not use source freshness, target freshness, surrounding-text-to-destination phrase relevance, field weights, silo features, or reranking logic in the FR-006 weight formula

### 5. Ranking regressions

Mitigation:

- keep `ranking_weight` default at `0.0`
- preserve `march_2026_pagerank_score` and all existing ranking math
- add parity tests that prove unchanged ranking when FR-006 ranking weight is zero

### 6. Performance regression on large graphs

Mitigation:

- keep sparse-matrix approach
- reuse current node-loading shape from `pagerank.py`
- calculate per-source normalized weights once per run, not per iteration
- persist only small stable edge features

## Exact Repo Modules / Files Likely To Be Touched

### Graph extraction and persistence

- `backend/apps/pipeline/services/link_parser.py`
- `backend/apps/graph/services/graph_sync.py`
- `backend/apps/graph/models.py`
- `backend/apps/graph/admin.py`
- `backend/apps/graph/tests.py`
- `backend/apps/graph/migrations/<new migration>`

### Authority computation

- `backend/apps/pipeline/services/pagerank.py` or a new sibling service such as `backend/apps/pipeline/services/weighted_pagerank.py`
- `backend/apps/pipeline/tasks.py`
- `backend/apps/pipeline/tests.py`

### Content and ranking

- `backend/apps/content/models.py`
- `backend/apps/content/serializers.py`
- `backend/apps/content/views.py`
- `backend/apps/content/admin.py`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/ranker.py`

### Suggestions and review

- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/suggestions/migrations/<new migration>`
- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`

### Settings and API

- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

## Test Plan

### 1. Uniform-weight parity behavior

- Build a small synthetic graph where every outgoing link has the same FR-006 feature values.
- Assert `march_2026_pagerank_score` stays bounded and deterministic.
- Assert ranking order is unchanged when `ranking_weight = 0.0`.

### 2. Monotonicity

- In a small graph with one source linking to two targets, increase only one edge's favorable features:
  - earlier ordinal
  - contextual instead of isolated
  - anchor instead of bare URL
- Assert that edge's normalized outbound probability rises.
- Assert the favored destination's March 2026 PageRank does not decrease in the simple graph.

### 3. Boundedness

- Assert every outbound weighted row sums to `1.0` within tolerance.
- Assert all March 2026 PageRank scores are non-negative.
- Assert all scores sum to `1.0` after convergence.

### 4. Normalization stability

- Feed rows with null FR-006 features.
- Feed rows with malformed data that would otherwise create non-finite raw scores.
- Assert the implementation falls back to uniform outbound probability for the affected source row.

### 5. Boilerplate down-weighting

- Create a source page with:
  - one early contextual anchor link
  - one late isolated bare URL
- Assert the early contextual anchor gets the higher normalized edge probability.

### 6. Contextual or editorial up-weighting

- Same source, same approximate position, different link types:
  - explicit anchor in prose
  - naked URL
- Assert the prose anchor wins.

### 7. Ordered extraction correctness

- Mixed BBCode, HTML, and bare URLs in one source body.
- Assert `link_ordinal` follows true source order, not regex-family order.
- Assert same-destination duplicates keep the earliest occurrence.

### 8. Existing-link persistence correctness

- Change an existing source post so an edge keeps the same source and destination but moves position or changes context class.
- Assert `sync_existing_links(...)` updates the FR-006 feature fields in place.

### 9. Migration away from `pagerank_score`

- Assert `march_2026_pagerank_score` is stored on `ContentItem`.
- Assert the old `pagerank_score` field is removed.

### 10. Diagnostics correctness

- Serializer tests:
  - `ContentItem` detail includes `march_2026_pagerank_score`
  - `SuggestionDetail` includes `score_march_2026_pagerank`
- Admin tests:
  - new fields are present and read-only where expected
- Frontend contract test or smoke test:
  - review dialog renders the `March 2026 PageRank` label

### 11. Settings validation and recalculation flow

- Invalid values outside bounds return `400`.
- Saving valid settings persists to `AppSetting`.
- Recalculation endpoint returns `202`.
- After recalculation, `march_2026_pagerank_score` changes as expected.

## Implementation Decision

Path chosen: **Path B**.

The source material is sufficient for a defensible FR-006 implementation specification if the repo uses:

- a conservative, deterministic link-weight heuristic;
- explicit per-source outbound normalization;
- separate persistence for March 2026 PageRank and the other ranking signals;
- opt-in ranking influence by default;
- clear phase boundaries that keep later features out of this slice.


