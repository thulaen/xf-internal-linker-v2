# FR-007 - Link Freshness Authority

## Confirmation

- Active phase confirmed: `Phase 10 / FR-007 - Link Freshness Authority` is still the next real target in `AI-CONTEXT.md`.
- Spec-first confirmed: `AI-CONTEXT.md` says patent-derived math phases require a spec pass before any implementation pass.
- Repo confirmed: no FR-007 spec file exists yet in `docs/specs/`.
- Repo confirmed: freshness-like logic already exists in `backend/apps/pipeline/services/velocity.py`, but that logic is for content recency and engagement, not link-history freshness.
- Repo confirmed: `backend/apps/graph/models.py` only stores active links today. It does not preserve enough link-history state to calculate appearance/disappearance trends for FR-007.

## Current Repo Map

### Active link graph today

- `backend/apps/graph/models.py`
  - `ExistingLink` stores active internal links only.
  - It keeps `discovered_at`, but there is no persistent `last_seen_at`, `last_disappeared_at`, or inactive-history row.
- `backend/apps/graph/services/graph_sync.py`
  - Reconciles parsed edges into active `ExistingLink` rows.
  - Deletes rows that disappear from the current parse result.
- `backend/apps/pipeline/tasks.py`
  - Full imports call `sync_existing_links(...)`, `refresh_existing_links()`, `run_weighted_pagerank()`, and `run_velocity(...)`.

### Current authority and ranking signals

- `backend/apps/pipeline/services/weighted_pagerank.py`
  - Computes `ContentItem.march_2026_pagerank_score`.
- `backend/apps/pipeline/services/velocity.py`
  - Computes `ContentItem.velocity_score`.
  - Uses content metrics, last activity, orphan state, and thin-content penalties.
  - This is not link-history freshness and must remain separate.
- `backend/apps/pipeline/services/ranker.py`
  - Uses host quality from `march_2026_pagerank_score`.
  - Can optionally add destination weighted authority through `weighted_authority_ranking_weight`.
  - Does not currently add `velocity_score` to `score_final`.

### Current review and API surfaces

- `backend/apps/content/models.py`
  - Stores `march_2026_pagerank_score` and `velocity_score`.
- `backend/apps/content/views.py`
  - Allows ordering by `march_2026_pagerank_score` and `velocity_score`.
- `backend/apps/suggestions/models.py`
  - Stores `score_march_2026_pagerank` and `score_velocity`.
- `backend/apps/suggestions/serializers.py`
  - Exposes those fields to review.
- `frontend/src/app/review/suggestion.service.ts`
  - Review detail type already includes PageRank and velocity.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - Review UI already shows both values.

## Problem Summary

Simple version first.

The app knows which links exist right now. It does not know enough about when those links first appeared, when they were last seen, or when they disappeared. Because of that, it cannot tell the difference between:

- a destination that is getting new editorial links now;
- a destination whose inbound links have gone quiet;
- a destination whose old links are disappearing.

That gap matters because `FR-007` is supposed to measure link freshness and link growth. It is not supposed to reuse `FR-006` edge-weight features, and it is not supposed to reuse the repo's existing `velocity` score.

## Goal

Add a separate, explainable, bounded link-history freshness signal for destinations.

The signal must:

- use internal-link appearance and disappearance history;
- treat unique source pages as the peer-link unit;
- stay neutral when history is missing or too thin;
- remain separate from `march_2026_pagerank_score`;
- remain separate from `velocity_score`;
- support review diagnostics plus content sorting/filtering;
- fit the current Django + Celery + PostgreSQL architecture.

## Non-goals

This phase does not:

- change FR-006 edge weighting;
- reuse `ExistingLink.extraction_method`, `link_ordinal`, `source_internal_link_count`, `context_class`, or anchor text as freshness inputs;
- reuse content `view_count`, `reply_count`, `download_count`, `post_date`, or `last_post_date` from `velocity.py`;
- change embeddings, distillation, anchors, silos, click-distance, reranking, clustering, or diversity logic;
- add telemetry, trend alerts, or model-promotion behavior from later phases;
- implement production code in this session.

## Source Summary From US8407231B2

Source actually read:

- [US8407231B2 - Document scoring based on link-based criteria](https://patents.google.com/patent/US8407231B2/en)

Patent ideas used here:

- Links can have an appearance date and a disappearance date.
- A system can monitor when links appear or disappear, how many appear or disappear during a period, and whether the trend is moving up or down over time.
- A downward trend in new links can signal staleness.
- An upward trend in new links can signal freshness.
- The patent explicitly allows comparing:
  - new links in a recent period versus total links;
  - the oldest appearance date of the newest group of links versus the oldest link overall;
  - growth from independent peer documents.
- The patent also describes adjusting an initial link-based score with a freshness-related history factor.

Patent ideas deliberately not used here:

- query-click behavior;
- document-content change dates as the main signal;
- spam heuristics tied to sudden spikes;
- any learned model over link-date distributions.

## Math-Fidelity Note

### Directly supported by the patent

- Use link appearance dates.
- Use link disappearance dates.
- Compare recent link growth to older link growth.
- Compare recent new-link concentration to total history.
- Compare the newest-link cohort to the oldest link history.
- Treat independent source documents as the peer unit.

### Adapted for this repo

- Inference: this repo does not have web-crawler timestamps, so FR-007 should use sync-detected timestamps as the appearance/disappearance clock.
- Inference: a unique `source ContentItem -> destination ContentItem` pair is the right local version of the patent's "independent peer document" idea.
- Inference: because the live ranker is additive and bounded today, FR-007 should expose a separate centered freshness signal and gate its ranking effect with a dedicated weight that defaults to `0.0`.

### Not carried over from the patent

- We are not using the patent's query-dependent staleness branches.
- We are not using traffic or user-click freshness.
- We are not using anchor-change freshness or content-change freshness in FR-007 v1.
- We are not using the patent's `H = L / log(F + 2)` inception-date example as the primary FR-007 formula because that branch is document-age based, while this feature request is specifically about link appearance/disappearance history.

## Scope Boundary Versus FR-006 and Later Phases

FR-007 must stay separate from:

- `FR-006`
  - no reuse of weighted-edge prominence fields;
  - no changes to `march_2026_pagerank_score` math;
  - no collapsing freshness into FR-006 authority.
- current `velocity` logic
  - no reuse of content recency, reply growth, download growth, or orphan multipliers;
  - no re-labeling `velocity_score` as freshness authority.
- later phases
  - `FR-008`: phrase/context relevance;
  - `FR-018`: auto-tuned weights;
  - `FR-019`: operator trend alerts;
  - `FR-020`: runtime model lifecycle.

Hard rule:

- FR-007 uses only link-history timing and peer-link counts.

## Inputs Required

FR-007 needs a persistent history row per unique source-to-destination peer edge.

Required per-history-row inputs:

- source content item
- destination content item
- `first_seen_at`
- `last_seen_at`
- `last_disappeared_at` or equivalent inactive marker
- `is_active`

Required per-calculation inputs:

- current calculation timestamp `t`
- `recent_window_days`
- `newest_peer_percent`
- `min_peer_count`
- component weights

Operational rule:

- disappearance updates are only valid when the source body was actually parsed in that sync/import pass.
- A title-only sync or any pass that did not parse a source body must not mark links as disappeared.

## Neutral Fallback Behavior When Inputs Are Missing

Missing or thin data must be neutral, not a hidden penalty.

Use a stored neutral score of `0.5` when any of these are true:

- no history rows exist for the destination;
- fewer than `min_peer_count` historical inbound peer rows exist;
- timestamps needed for the calculation are missing or invalid after filtering;
- the destination has history rows but they do not cover enough time to compare recent and previous windows safely.

Neutral behavior rules:

- `0.5` means "unknown or inconclusive," not "bad."
- Ranking effect for a neutral score must be `0.0`.
- Review UI should label this state as `Neutral / not enough link history`.

## Proposed Scoring Or Decay Logic

Simple version first.

Each destination gets a separate link-freshness score from `0.0` to `1.0`.

- `1.0` means strongly fresh
- `0.5` means neutral
- `0.0` means strongly stale

The signal only looks at unique inbound peer links over time.

### History row definition

One FR-007 history row represents one unique:

- `from_content_item`
- `to_content_item`

pair.

Anchor text is not part of the FR-007 identity.

Reason:

- the patent talks about links from peer documents;
- the repo already treats `source -> destination` as the stable graph relationship for authority;
- using anchor text here would create fake growth when only anchor wording changes.

### Per-destination counts

For destination `d` at calculation time `t`:

- `total_peers(d)` = all historical inbound peer rows for `d`
- `recent_new(d)` = peer rows where `first_seen_at >= t - recent_window`
- `previous_new(d)` = peer rows where `t - 2 * recent_window <= first_seen_at < t - recent_window`
- `recent_lost(d)` = peer rows where `is_active = false` and `last_disappeared_at >= t - recent_window`

### Per-destination cohort ages

Let:

- `k = max(1, ceil(total_peers(d) * newest_peer_percent))`
- `oldest_peer_age_days(d)` = age in days of the oldest `first_seen_at`
- `oldest_recent_cohort_age_days(d)` = age in days of the oldest `first_seen_at` inside the newest `k` peer rows

### Component formulas

If `total_peers(d) < min_peer_count`, stop and return `0.5`.

Otherwise compute:

- `recent_share(d) = recent_new(d) / total_peers(d)`
- `growth_delta(d) = clamp((recent_new(d) - previous_new(d)) / total_peers(d), -1.0, 1.0)`
- `cohort_freshness(d) = 1.0 - clamp(oldest_recent_cohort_age_days(d) / max(oldest_peer_age_days(d), 1.0), 0.0, 1.0)`
- `loss_share(d) = recent_lost(d) / total_peers(d)`

Centered components:

- `recent_component(d) = 2 * recent_share(d) - 1`
- `cohort_component(d) = 2 * cohort_freshness(d) - 1`

Combined centered signal:

```text
freshness_centered(d) =
  clamp(
    w_recent * recent_component(d)
    + w_growth * growth_delta(d)
    + w_cohort * cohort_component(d)
    - w_loss * loss_share(d),
    -1.0,
    1.0
  )
```

Stored score:

```text
link_freshness_score(d) = 0.5 + 0.5 * freshness_centered(d)
```

### Why this matches the patent well enough

- `recent_share` matches the patent's recent-new-links versus total-links idea.
- `growth_delta` matches the patent's upward/downward trend idea.
- `cohort_freshness` matches the patent's newest-link-group versus oldest-link-history idea.
- `loss_share` matches the patent's disappearance-date idea.

### Why this is safe for this repo

- It is deterministic.
- It is bounded.
- It is explainable with simple counts.
- It does not depend on user traffic.
- It does not depend on FR-006 edge-prominence fields.

## Normalization And Bounds

Stored content score:

- `ContentItem.link_freshness_score` in `[0.0, 1.0]`
- neutral default is `0.5`

Stored suggestion score:

- `Suggestion.score_link_freshness` in `[0.0, 1.0]`
- copy of the destination's stored `link_freshness_score`

Centered ranker component:

```text
score_link_freshness_component = 2 * (link_freshness_score - 0.5)
```

This makes:

- `0.5 -> 0.0` effect
- `1.0 -> +1.0` effect
- `0.0 -> -1.0` effect

Fresh/stale buckets for filtering:

- `fresh` when `link_freshness_score >= 0.60`
- `neutral` when `0.40 < link_freshness_score < 0.60`
- `stale` when `link_freshness_score <= 0.40`

## Settings And Defaults

Persist through `AppSetting` in category `link_freshness`.

Required settings:

- `link_freshness.ranking_weight`
- `link_freshness.recent_window_days`
- `link_freshness.newest_peer_percent`
- `link_freshness.min_peer_count`
- `link_freshness.w_recent`
- `link_freshness.w_growth`
- `link_freshness.w_cohort`
- `link_freshness.w_loss`

Defaults:

- `ranking_weight = 0.0`
- `recent_window_days = 30`
- `newest_peer_percent = 0.25`
- `min_peer_count = 3`
- `w_recent = 0.35`
- `w_growth = 0.35`
- `w_cohort = 0.20`
- `w_loss = 0.10`

Validation rules:

- `0.0 <= ranking_weight <= 0.15`
- `7 <= recent_window_days <= 90`
- `0.10 <= newest_peer_percent <= 0.50`
- `1 <= min_peer_count <= 20`
- every component weight must be finite and in `[0.0, 1.0]`
- `w_recent + w_growth + w_cohort + w_loss` must equal `1.0`

Ranking rule:

```text
score_final += ranking_weight * score_link_freshness_component
```

Default safety rule:

- with `ranking_weight = 0.0`, FR-007 does not change ranking order.

## Diagnostics And Explainability

Review and admin should expose both the stored score and the simple numbers behind it.

Required detail diagnostics for one destination:

- `link_freshness_score`
- `freshness_bucket`
- `freshness_data_state`
  - `computed`
  - `neutral_missing_history`
  - `neutral_thin_history`
  - `neutral_invalid_history`
- `total_peer_count`
- `active_peer_count`
- `recent_new_peer_count`
- `previous_new_peer_count`
- `recent_lost_peer_count`
- `recent_share`
- `growth_delta`
- `cohort_freshness`
- `recent_window_days`
- `newest_peer_percent`
- `min_peer_count`

Required review label:

- `Link Freshness`

Required plain-English helper text:

- `Fresh means this destination has newer or growing inbound links.`
- `Stale means newer inbound-link growth has cooled off or links have recently disappeared.`
- `Neutral means there is not enough link history yet.`

## Storage Impact, If Any

Storage impact is required.

### New history model

Add a new model in `backend/apps/graph/models.py`.

Recommended name:

- `LinkFreshnessEdge`

Required fields:

- `from_content_item`
- `to_content_item`
- `first_seen_at`
- `last_seen_at`
- `last_disappeared_at` nullable
- `is_active`

Required uniqueness:

- unique on `from_content_item` + `to_content_item`

Recommended indexes:

- `Index(fields=["to_content_item", "is_active"])`
- `Index(fields=["to_content_item", "first_seen_at"])`
- `Index(fields=["to_content_item", "last_disappeared_at"])`

### New content field

Add to `backend/apps/content/models.py`:

- `link_freshness_score: FloatField(default=0.5, db_index=True)`

### New suggestion field

Add to `backend/apps/suggestions/models.py`:

- `score_link_freshness: FloatField(default=0.5)`

### Existing data kept as-is

- `ExistingLink` remains the active graph table for FR-006 and duplicate-link suppression.
- `ExistingLink.discovered_at` stays as a first-detected admin aid. It is not enough to replace the FR-007 history model.

## API/Admin Impact, If Any

### Backend API

Add:

- `GET /api/settings/link-freshness/`
- `PUT /api/settings/link-freshness/`
- `POST /api/settings/link-freshness/recalculate/`

Recalculate endpoint behavior:

- dispatch a Celery task;
- recompute `ContentItem.link_freshness_score` from stored history rows and current settings;
- leave old scores untouched if the task fails.

### Content API

Expose on content list/detail:

- `link_freshness_score`
- optional `freshness_bucket`

Allow ordering by:

- `link_freshness_score`

Allow filtering by:

- `freshness_bucket`

### Suggestion API

Expose on suggestion detail:

- `score_link_freshness`
- a small `link_freshness_diagnostics` object

### Admin

Add read-only surfacing for:

- `ContentItem.link_freshness_score`
- `Suggestion.score_link_freshness`
- `LinkFreshnessEdge` rows

### Frontend

Later implementation should add:

- one review score row for `Link Freshness`
- filter chips or select options for `fresh`, `neutral`, `stale`
- content sorting option for `link_freshness_score`

## Rollout Plan

Use a safe staged rollout.

### Step 1 - collect history only

- start writing `LinkFreshnessEdge` rows during full-body sync/import work;
- do not change ranker behavior;
- keep `ranking_weight = 0.0`.

### Step 2 - backfill and calculate

- run a recalculation job after enough history exists;
- populate `ContentItem.link_freshness_score`;
- expose read-only diagnostics in admin and review.

### Step 3 - optional ranking enablement

- keep `ranking_weight = 0.0` by default;
- only enable a small non-zero weight after verification passes and operator review agrees with the behavior.

## Rollback Plan

Immediate rollback:

- set `link_freshness.ranking_weight = 0.0`
- stop using the score in `score_final`

Operational rollback:

- leave stored history rows in place;
- keep `ContentItem.link_freshness_score` for inspection;
- disable or hide FR-007 review filters if they confuse the operator.

Failure rollback:

- if a recalculation task fails, do not zero all scores;
- keep the last good `link_freshness_score` values;
- surface the task failure to the existing job/error paths;
- FR-006 PageRank and current review flows must continue working unchanged.

Schema rollback note:

- because history rows are additive and separate from `ExistingLink`, FR-007 can be turned off without rolling back FR-006 storage or graph sync behavior.

## Test Plan

### 1. Neutral fallback

- destination with no history rows returns `0.5`
- destination with fewer than `min_peer_count` rows returns `0.5`
- invalid timestamps after filtering return `0.5`

### 2. Recent growth

- create a destination with more new inbound peers in the recent window than in the previous window
- assert `link_freshness_score > 0.5`

### 3. Cooling growth

- create a destination with fewer new inbound peers in the recent window than in the previous window
- assert `link_freshness_score < 0.5`

### 4. Recent disappearance pressure

- mark several recent peer rows inactive with fresh `last_disappeared_at`
- assert the score falls relative to the same data without disappearances

### 5. Cohort age behavior

- one destination has a very new newest cohort
- another has an old newest cohort
- assert the first gets a higher score

### 6. Neutral ranking effect

- with `ranking_weight = 0.0`, candidate ordering remains unchanged
- with a destination score of `0.5`, FR-007 contributes exactly `0.0`

### 7. Sync behavior

- full-body sync of a source that still contains the link updates `last_seen_at`
- full-body sync of a source that dropped the link sets `is_active = false` and `last_disappeared_at`
- title-only sync does not mark links disappeared

### 8. Reactivation behavior

- a previously inactive peer link that reappears becomes active again
- `first_seen_at` stays unchanged
- the row remains one peer row, not a duplicate row

### 9. Serializer and ordering coverage

- content endpoints expose `link_freshness_score`
- suggestion detail exposes `score_link_freshness`
- content ordering by `link_freshness_score` works
- bucket filter works

### 10. Boundary checks

- changing FR-006 weighted-edge settings does not change FR-007 inputs
- changing velocity settings does not change FR-007 inputs
- FR-007 recalculation does not rewrite `march_2026_pagerank_score`

## Risks And Open Questions

### Risks

- History starts empty, so the score will be neutral for a while.
- Partial sync coverage can create false disappearance signals if implementation is careless.
- Very small sites may rarely reach `min_peer_count`.
- Link flapping can blur the meaning of "new" versus "reappeared" if implementation gets too clever.

### Open questions

1. Should a reappeared peer link count as "new" again in v1?
   - Proposed answer for v1: no. Keep one peer row and preserve the original `first_seen_at`.
2. Should FR-007 show the score on the suggestion list, not just detail?
   - Proposed answer for v1: detail first, list sorting/filtering second.
3. Should the content API expose raw diagnostics counts or only the final score and bucket?
   - Proposed answer for v1: expose the final score everywhere, and raw diagnostics on detail screens only.

## Exact Repo Modules Likely To Be Touched In The Later Implementation Session

### Graph and sync

- `backend/apps/graph/models.py`
- `backend/apps/graph/admin.py`
- `backend/apps/graph/services/graph_sync.py`
- `backend/apps/graph/migrations/<new migration>`

### Scoring and tasks

- `backend/apps/pipeline/tasks.py`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/<new fr007 freshness service>`
- `backend/apps/pipeline/tests.py`

### Content and suggestions

- `backend/apps/content/models.py`
- `backend/apps/content/serializers.py`
- `backend/apps/content/views.py`
- `backend/apps/content/admin.py`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/suggestions/migrations/<new migration>`

### Settings and review UI

- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

## Implementation Decision

Path chosen for the repo:

- keep this session spec-first only;
- add a separate link-history freshness score;
- keep missing data neutral;
- keep ranking impact off by default;
- keep FR-006 and `velocity` untouched except for later additive integration points that are clearly scoped to FR-007.
