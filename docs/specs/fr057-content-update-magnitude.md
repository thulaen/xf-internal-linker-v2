# FR-057 - Content-Update Magnitude

## Confirmation

- **Backlog confirmed**: `FR-057 - Content-Update Magnitude` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No content-change-magnitude signal exists in the current ranker. The closest existing signal is link freshness (FR-007), which measures when links appeared or disappeared. FR-057 measures how much the *content itself* changed between crawls — a fundamentally different axis. A page can have a recent timestamp (freshness) with zero real content change (cosmetic edit), or substantial content change with no link movement.
- **Repo confirmed**: `ContentItem.distilled_text` is stored per crawl. Previous crawl snapshots can be compared to current ones using token-level set operations.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_link_freshness` (FR-007) — measures link appearance/disappearance timing.
  - No signal currently measures the *substance* of content edits.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns a normalized token set. Reusable for computing token-level diffs.

### Source data already available at pipeline time

- `backend/apps/content/models.py`
  - `ContentItem` stores `distilled_text` and `last_crawled` timestamp.
  - Previous crawl snapshots are available if content history tracking is enabled.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US8549014B2 — Document Scoring Based on Document Content Update

**Plain-English description of the patent:**

The patent describes a system that scores documents based on the *magnitude* of their content changes, not just the timestamp of the last modification. It distinguishes between substantial updates (significant text rewritten, new sections added, factual corrections) and trivial changes (copyright year bumped, ad block rotated, whitespace reformatted). Documents with substantive recent updates score higher because they represent actively maintained, reliable content.

**Repo-safe reading:**

The patent operates on web-scale change detection. This repo adapts the idea to site-local content: compare the current crawl's `distilled_text` against the previous crawl's `distilled_text` using token-level symmetric difference. The reusable core idea is:

- a page that changed its copyright year from 2024 to 2025 has not meaningfully updated;
- a page that rewrote 2000 words of its body has substantively updated;
- the fraction of tokens that changed between crawls measures update magnitude;
- prefer linking to pages that are actively maintained with real content updates.

**What is directly supported by the patent:**

- measuring document change magnitude beyond timestamp inspection;
- using token-level difference as a change metric;
- treating substantive updates as a positive quality signal.

**What is adapted for this repo:**

- "document versions" map to successive crawl snapshots of `distilled_text`;
- the patent uses shingle hashing for change detection; this repo uses simple token set symmetric difference;
- the signal is applied as a per-page quality score cached at crawl time.

## Plain-English Summary

Simple version first.

Some pages show a "last updated" date that makes them look fresh, but the only thing that changed was a footer copyright year or an ad block rotation. The actual content is the same as it was two years ago. Other pages have been substantially rewritten with new information, corrections, and expanded sections.

FR-057 catches the difference. It compares the current version of a page's content against the previous crawl version, token by token, and measures what fraction of the content actually changed. A page where 40% of the tokens are new or different has had a substantial update. A page where 1% of the tokens changed has had a cosmetic edit.

This is different from link freshness (which tracks when links appeared or disappeared) and from seasonality (which matches demand cycles). FR-057 asks "has the content on this page actually been meaningfully updated?"

## Problem Statement

Today the ranker has no way to distinguish between a page with a genuine recent content overhaul and a page that merely updated its copyright footer. Both have recent "last modified" timestamps, but only one represents actively maintained, trustworthy content.

This means the ranker treats a stale page with a cosmetic timestamp bump identically to a genuinely refreshed page. The reader who follows a link to the stale page finds outdated information despite the "recently updated" appearance.

FR-057 closes this gap by measuring the actual magnitude of content changes.

## Goals

FR-057 should:

- add a separate, explainable, bounded content-update-magnitude signal;
- compute the token-level symmetric difference between the current and previous crawl versions;
- express the result as a fraction of tokens that changed (update magnitude);
- penalize pages that have not been substantively updated within `max_staleness_days`;
- keep pages with recent substantive updates scored positively;
- keep pages with no previous crawl snapshot neutral at `0.5`;
- compute the magnitude at crawl time (not at suggestion time) since it is a per-page property;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-057 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-056 logic;
- replace link freshness (FR-007) — they measure different things;
- implement full version history or diff visualization in v1;
- use analytics, reviewer feedback, or any live query data;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `T_curr` = normalized token set of the current crawl's `distilled_text`
- `T_prev` = normalized token set of the previous crawl's `distilled_text`
- `days_since_update` = days since the most recent crawl where the token set changed substantively

**Token symmetric difference:**

```text
changed_tokens = (T_curr - T_prev) ∪ (T_prev - T_curr)
```

(tokens that are in one version but not the other — additions and removals combined)

**Update magnitude:**

```text
update_magnitude = len(changed_tokens) / max(len(T_curr ∪ T_prev), 1)
```

This is the fraction of the combined vocabulary that changed between crawls.

- `update_magnitude = 0.0` — page is identical between crawls (no real update)
- `update_magnitude = 0.40` — 40% of the vocabulary changed (substantial rewrite)
- `update_magnitude = 1.0` — completely different content (total replacement)

**Staleness decay:**

```text
if days_since_update > max_staleness_days:
    staleness_factor = max(0.0, 1.0 - (days_since_update - max_staleness_days) / max_staleness_days)
else:
    staleness_factor = 1.0
```

This applies a linear decay to pages that have not had a substantive update in a long time. Pages updated within `max_staleness_days` get no staleness penalty.

**Bounded score:**

```text
score_content_update = 0.5 + 0.5 * update_magnitude * staleness_factor
```

This maps:

- recent substantial update (magnitude=0.4, factor=1.0) -> `score = 0.5 + 0.5 * 0.4 = 0.70`
- recent cosmetic update (magnitude=0.01, factor=1.0) -> `score = 0.5 + 0.5 * 0.01 = 0.505`
- old substantial update (magnitude=0.4, factor=0.3) -> `score = 0.5 + 0.5 * 0.12 = 0.56`
- no previous crawl -> `score = 0.5` (neutral)

**Neutral fallback:**

```text
score_content_update = 0.5
```

Used when:

- no previous crawl snapshot exists for this page;
- feature is disabled.

### Why symmetric difference is the right metric

One-sided difference (only additions or only removals) misses the full picture. A page that replaced 500 old tokens with 500 new tokens has a massive update, but unidirectional difference would only show 500 changes. Symmetric difference captures both additions and removals, giving the true extent of content change. Dividing by the union normalizes for page length — a 50-word change on a 100-word page is more significant than a 50-word change on a 10,000-word page.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_content_update_component =
  max(0.0, min(1.0, 2.0 * (score_content_update - 0.5)))
```

```text
score_final += content_update.ranking_weight * score_content_update_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-057 must stay separate from:

- link freshness (FR-007)
  - link freshness measures when links appeared or disappeared;
  - FR-057 measures how much the page content itself changed;
  - a page can have fresh links but stale content, or vice versa.

- seasonality (FR-050)
  - seasonality matches temporal demand patterns;
  - FR-057 measures content maintenance quality;
  - a seasonal page can be actively maintained or stale.

- `score_information_gain` (FR-038)
  - information gain measures what the destination adds relative to the source;
  - FR-057 measures what the destination changed relative to its own previous version;
  - one is cross-page, the other is intra-page temporal.

- `score_semantic`
  - semantic measures topical similarity;
  - FR-057 measures content currency;
  - orthogonal axes.

Hard rule: FR-057 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-057 v1 needs:

- current `distilled_text` — from the current crawl's `ContentItem`
- previous `distilled_text` — from the previous crawl snapshot (requires content history)
- `tokenize_text(...)` — existing normalizer in `text_tokens.py`
- crawl timestamps — from `ContentItem.last_crawled`

Explicitly disallowed FR-057 inputs in v1:

- raw HTML diffs (too noisy — template changes would dominate)
- embedding-level change detection
- analytics or telemetry data
- any data not available from the content crawl pipeline

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `content_update.enabled`
- `content_update.ranking_weight`
- `content_update.max_staleness_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `max_staleness_days = 180`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `30 <= max_staleness_days <= 730`

### Feature-flag behavior

- `enabled = false`
  - skip update magnitude computation entirely
  - store `score_content_update = 0.5`
  - store `content_update_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute update magnitudes and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.content_update_diagnostics`

Required fields:

- `score_content_update`
- `content_update_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_no_previous_crawl`
  - `neutral_processing_error`
- `update_magnitude` — fraction of tokens that changed
- `changed_token_count` — number of tokens in the symmetric difference
- `union_token_count` — number of tokens in the combined vocabulary
- `days_since_update` — days since the last substantive content change
- `staleness_factor` — decay factor applied
- `sample_added_tokens` — up to 5 example tokens that were added (new in current version)
- `sample_removed_tokens` — up to 5 example tokens that were removed (gone from current version)
- `max_staleness_days_setting` — setting value used for this run

Plain-English review helper text should say:

- `Content update magnitude means this destination page has been genuinely updated with new content, not just cosmetically refreshed.`
- `A high score means the page has recent, substantial edits — new paragraphs, rewritten sections, or factual corrections.`
- `Neutral means there is no previous crawl to compare against, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_content_update: FloatField(default=0.5)`
- `content_update_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.update_magnitude: FloatField(null=True, blank=True)`
- `ContentItem.last_substantive_update: DateTimeField(null=True, blank=True)`

Reason:

- update magnitude is a per-page property computed at crawl time;
- caching it avoids recomputing token diffs at suggestion time.

A content history mechanism is needed:

- Option A: store `previous_distilled_text` as a separate field on ContentItem (simple, doubles text storage)
- Option B: use a `ContentHistory` model with FK to ContentItem (more scalable, allows multi-version diffs)

Recommended: Option A for v1 (simpler). Option B for future work if multi-version history is needed.

### PipelineRun snapshot

Add FR-057 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/content-update/`
- `PUT /api/settings/content-update/`

No recalculation endpoint in v1. Update magnitudes are recomputed automatically during re-crawl.

### Review / admin / frontend

Add one new review row:

- `Content Update`

Add one small diagnostics block:

- update magnitude (percentage)
- changed token count vs union token count
- days since last substantive update
- sample added/removed tokens (up to 5 each)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- maximum staleness days input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/content_update.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-057 additive hook
- `backend/apps/pipeline/services/pipeline.py` — read cached update magnitude at suggestion time
- `backend/apps/pipeline/services/text_tokens.py` — reuse existing `tokenize_text()`
- `backend/apps/content/models.py` — add update_magnitude and last_substantive_update fields (+ previous_distilled_text for v1)
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-057 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-057 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-057 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`
- FR-007 link freshness logic — must remain independent

## Test Plan

### 1. Token symmetric difference

- identical content between crawls -> `update_magnitude = 0.0`, `score = 0.5`
- completely different content -> `update_magnitude = 1.0`, `score = 1.0`
- 50% token overlap -> magnitude proportional to symmetric difference

### 2. Staleness decay

- update within `max_staleness_days` -> `staleness_factor = 1.0`
- update at `2 * max_staleness_days` -> `staleness_factor = 0.0`
- update at `1.5 * max_staleness_days` -> `staleness_factor = 0.5`

### 3. Neutral fallback cases

- no previous crawl snapshot -> `score = 0.5`, state `neutral_no_previous_crawl`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in `[0.5, 1.0]` regardless of input

### 6. Isolation from other signals

- changing FR-007 link freshness does not affect `score_content_update`
- changing FR-050 seasonality does not affect `score_content_update`
- update_magnitude is stored on ContentItem but never modifies `distilled_text` or embeddings

### 7. Serializer and frontend contract

- `score_content_update` and `content_update_diagnostics` appear in suggestion detail API response
- review dialog renders the `Content Update` row
- settings page loads and saves FR-057 settings

### 8. Sample token cap

- `sample_added_tokens` contains at most 5 entries
- `sample_removed_tokens` contains at most 5 entries

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-057 settings and algorithm version

## Rollout Plan

### Step 1 — crawl-time computation

- implement token diff computation during re-crawl
- store update_magnitude and last_substantive_update on ContentItem
- verify magnitudes look sensible

### Step 2 — diagnostics only

- implement FR-057 scoring with `ranking_weight = 0.0`
- verify that high-magnitude pages genuinely had substantive content changes
- verify that low-magnitude pages had only cosmetic edits

### Step 3 — operator review

- inspect `sample_added_tokens` and `sample_removed_tokens` for representative changes
- confirm staleness decay behaves as expected for old pages

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.01` to `0.03`

## Risk List

- token-level diff does not capture semantic significance — rewriting a sentence with synonyms looks like a big change but may not add information. Mitigated by the conservative starting weight;
- pages that rotate ad text or seasonal greetings may show high update_magnitude for non-substantive changes — mitigated by using `distilled_text` (which should exclude ads) rather than raw HTML;
- storing `previous_distilled_text` doubles the text storage per page — mitigated by limiting to one previous version in v1;
- first crawl of a new page produces no previous snapshot, so all new pages start neutral — this is correct behavior, not a bug.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"content_update.enabled": "true",
"content_update.ranking_weight": "0.02",
"content_update.max_staleness_days": "180",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.02` — conservative because the signal partly overlaps with link freshness (FR-007) conceptually. Raise to `0.04` after confirming independence on live data.
- `max_staleness_days = 180` — pages not substantively updated in 6 months start to decay. This matches typical content lifecycle expectations for actively managed sites.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- multi-version content history (tracking more than one previous crawl)
- semantic-level change detection (embedding diff rather than token diff)
- per-section change tracking (which paragraph changed vs which stayed the same)
- diff visualization in the review UI (showing added/removed text inline)
- any dependency on analytics or telemetry data
- any modification to stored text or embeddings
