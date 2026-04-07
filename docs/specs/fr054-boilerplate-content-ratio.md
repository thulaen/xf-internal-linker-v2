# FR-054 - Boilerplate-to-Content Ratio

## Confirmation

- **Backlog confirmed**: `FR-054 - Boilerplate-to-Content Ratio` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No page-structure quality signal exists in the current ranker. The closest existing signal is near-duplicate clustering (FR-014), which catches copied content *across* pages. FR-054 catches template bloat *within* a single page — a fundamentally different axis.
- **Repo confirmed**: `ContentItem.distilled_text` is already extracted from raw HTML during crawling. FR-054 additionally needs the raw HTML (or a structural zone extraction) to determine which parts of the page are main content versus chrome (navigation, footer, sidebar).

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - No signal currently examines the structural composition of a destination page (content vs. template).
  - `score_information_gain` (FR-038) measures vocabulary novelty, not page structure.
  - `score_fact_density` (FR-042) measures factual claims, not content-to-chrome ratio.

- `backend/apps/content/models.py`
  - `ContentItem` stores `distilled_text` (main content extracted from HTML) and `raw_html` or equivalent crawl data.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Destination `ContentRecord` rows include `distilled_text` character counts.
  - Raw HTML or page structure metadata may be available from the crawl step.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US8898296B2 — Detection of Boilerplate Content

**Plain-English description of the patent:**

The patent describes a system that identifies which parts of a web page are "boilerplate" — repeated template elements like navigation menus, footers, sidebars, and legal notices — versus the unique main content. It uses DOM structure analysis and cross-page template detection to classify each text block as content or chrome.

**Repo-safe reading:**

The patent operates on raw DOM analysis across a large crawl. This repo adapts the idea to a simpler per-page measurement: compare the character count of `distilled_text` (main content) against the total text content of the page. The reusable core idea is:

- a page that is 80%+ boilerplate offers little unique value to a reader following a link;
- the ratio of main content to total page text is a quick, deterministic quality indicator;
- prefer linking to pages where the reader gets substantial unique content, not mostly template.

**What is directly supported by the patent:**

- classifying page regions as content or boilerplate;
- using the content-to-boilerplate ratio as a quality signal;
- applying the signal at document level.

**What is adapted for this repo:**

- instead of DOM-level zone classification, FR-054 v1 uses the ratio of `distilled_text` character count to total page text character count as a proxy;
- the patent classifies each DOM element; this repo uses the already-extracted `distilled_text` as the "content" portion;
- the signal is applied at suggestion time as an additive penalty for low-content-ratio destinations.

## Plain-English Summary

Simple version first.

Some web pages are mostly navigation menus, footers, sidebars, and boilerplate — the actual unique content is just a few sentences buried in the middle. When a reader clicks a link to one of these pages, they land on a page that is 80% template and 20% substance. That is a disappointing experience.

FR-054 measures what fraction of a destination page is actual main content versus template chrome. A page where 70% of the text is unique content scores well. A page where only 15% is content and the rest is menus and footers gets penalized.

This is different from near-duplicate clustering (which catches copied content between pages) and from information gain (which measures vocabulary novelty). FR-054 asks a simpler question: "how much of this page is actually worth reading?"

## Problem Statement

Today the ranker scores destination pages by topical relevance, authority, and content quality without considering how much of the destination page is actual content. A thin landing page with a massive navigation menu and a two-sentence main body scores the same as a substantial article — as long as the topic matches.

This means the ranker can recommend pages where the reader clicks through and finds mostly template. The page may technically be relevant, but the content-to-chrome ratio makes it a poor destination.

FR-054 closes this gap with a bounded content ratio score.

## Goals

FR-054 should:

- add a separate, explainable, bounded boilerplate-ratio signal;
- compute the ratio of main content characters to total page text characters per destination;
- penalize destinations where the content ratio falls below `boilerplate_threshold`;
- keep pages with healthy content ratios neutral (no penalty, no boost);
- keep missing or insufficient data neutral at `0.5`;
- compute the ratio at crawl/index time (not at suggestion time) since it is a per-page property;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-054 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-053 logic;
- implement DOM-level zone classification in v1 — it uses the simpler distilled-text ratio;
- replace the relevance requirement — a high content ratio does not override a low semantic score;
- use analytics, reviewer feedback, or any live query data;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `C` = character count of `distilled_text` (main content extracted by the crawler)
- `T` = character count of the total visible text on the page (all text nodes in the rendered DOM, including navigation, footer, sidebar text)
- `min_content_chars` = minimum content characters for a valid ratio (default 200)

**Content ratio:**

```text
content_ratio = C / max(T, 1)
```

This is the fraction of the page's visible text that is unique main content.

**Bounded score:**

```text
if content_ratio >= boilerplate_threshold:
    score_boilerplate_ratio = 1.0
elif C < min_content_chars:
    score_boilerplate_ratio = 0.5  (neutral fallback)
else:
    score_boilerplate_ratio = content_ratio / boilerplate_threshold
```

This maps:

- `content_ratio >= 0.80` (80%+ is content) -> `score = 1.0` (no penalty)
- `content_ratio = 0.40` (40% content, 60% chrome) -> `score = 0.40 / 0.80 = 0.50`
- `content_ratio = 0.10` (10% content, 90% chrome) -> `score = 0.10 / 0.80 = 0.125`

**Neutral fallback:**

```text
score_boilerplate_ratio = 0.5
```

Used when:

- `distilled_text` has fewer than `min_content_chars` characters;
- total page text count is unavailable;
- feature is disabled.

### Why content_ratio / threshold is the right formula

A linear ramp from 0 to 1 as content_ratio approaches the threshold is simple, predictable, and easy for operators to reason about. The threshold acts as a "good enough" line — pages above it are not penalized. Pages below it are penalized proportionally. This avoids cliff-edge behavior where a 79% content page gets hammered but an 81% page is untouched.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_boilerplate_ratio_component =
  max(0.0, min(1.0, 2.0 * (score_boilerplate_ratio - 0.5)))
```

```text
score_final += boilerplate_ratio.ranking_weight * score_boilerplate_ratio_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-054 must stay separate from:

- `score_semantic`
  - semantic measures topical similarity;
  - FR-054 measures page structural quality (content-to-chrome ratio);
  - completely different axes.

- `score_information_gain` (FR-038)
  - information gain measures vocabulary novelty (what the destination adds);
  - FR-054 measures how much of the destination page is actual content;
  - a page can have high novelty but be 90% boilerplate.

- near-duplicate clustering (FR-014)
  - clustering catches duplicated content *across* pages;
  - FR-054 catches template bloat *within* a single page;
  - one is cross-page, the other is intra-page.

- `score_fact_density` (FR-042)
  - fact density measures the proportion of factual claims within the content;
  - FR-054 measures how much of the page IS content in the first place;
  - FR-042 operates on the content portion; FR-054 measures the size of that portion.

Hard rule: FR-054 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-054 v1 can use only data already available or derivable from the crawl:

- destination `distilled_text` character count — from `ContentItem.distilled_text`
- total page text character count — derived from the crawl output (all visible text nodes)
- the ratio is computed at crawl time and cached on the `ContentItem`

Explicitly disallowed FR-054 inputs in v1:

- embedding vectors
- analytics or telemetry data
- reviewer-edited content
- any data not available at crawl/index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `boilerplate_ratio.enabled`
- `boilerplate_ratio.ranking_weight`
- `boilerplate_ratio.boilerplate_threshold`
- `boilerplate_ratio.min_content_chars`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `boilerplate_threshold = 0.80`
- `min_content_chars = 200`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.30 <= boilerplate_threshold <= 0.95`
- `50 <= min_content_chars <= 1000`

### Feature-flag behavior

- `enabled = false`
  - skip boilerplate computation entirely
  - store `score_boilerplate_ratio = 0.5`
  - store `boilerplate_ratio_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute content ratios and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.boilerplate_ratio_diagnostics`

Required fields:

- `score_boilerplate_ratio`
- `boilerplate_ratio_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_content_too_short`
  - `neutral_total_text_unavailable`
  - `neutral_processing_error`
- `content_chars` — character count of `distilled_text`
- `total_chars` — character count of total visible page text
- `content_ratio` — raw `content_chars / total_chars`
- `boilerplate_threshold_setting` — threshold used for this run
- `min_content_chars_setting` — minimum content chars used for this run

Plain-English review helper text should say:

- `Boilerplate ratio means the destination page has a healthy proportion of unique content versus template chrome.`
- `A high score means the reader will find mostly real content when they arrive, not just navigation and footer text.`
- `Neutral means the destination had too little content to measure, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_boilerplate_ratio: FloatField(default=0.5)`
- `boilerplate_ratio_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.content_ratio: FloatField(null=True, blank=True)`
- `ContentItem.total_text_chars: IntegerField(null=True, blank=True)`

Reason:

- content ratio is a stable per-page property computed at crawl time;
- caching it avoids redundant recalculation.

### PipelineRun snapshot

Add FR-054 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/boilerplate-ratio/`
- `PUT /api/settings/boilerplate-ratio/`

No recalculation endpoint in v1. Content ratios are recomputed automatically when a page is re-crawled.

### Review / admin / frontend

Add one new review row:

- `Boilerplate Ratio`

Add one small diagnostics block:

- content ratio (percentage)
- content chars vs total chars
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- boilerplate threshold input
- minimum content characters input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/boilerplate_ratio.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-054 additive hook
- `backend/apps/pipeline/services/pipeline.py` — read cached content ratios at suggestion time
- `backend/apps/content/models.py` — add `content_ratio` and `total_text_chars` fields
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-054 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-054 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-054 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`

## Test Plan

### 1. Content ratio computation

- page with 800 content chars out of 1000 total -> `content_ratio = 0.80`, `score = 1.0`
- page with 200 content chars out of 1000 total -> `content_ratio = 0.20`, `score = 0.25`
- page with 1000 content chars out of 1000 total -> `content_ratio = 1.0`, `score = 1.0`

### 2. Neutral fallback cases

- content has fewer than `min_content_chars` -> `score = 0.5`, state `neutral_content_too_short`
- total text count unavailable -> `score = 0.5`, state `neutral_total_text_unavailable`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 3. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 4. Bounded score

- score is always in `[0.0, 1.0]` regardless of input
- content_ratio is always in `[0.0, 1.0]`

### 5. Isolation from other signals

- changing `score_semantic` inputs does not affect `score_boilerplate_ratio`
- changing FR-014 clustering does not affect `score_boilerplate_ratio`
- content_ratio is stored on ContentItem but never modifies `distilled_text` or embeddings

### 6. Serializer and frontend contract

- `score_boilerplate_ratio` and `boilerplate_ratio_diagnostics` appear in suggestion detail API response
- review dialog renders the `Boilerplate Ratio` row
- settings page loads and saves FR-054 settings

### 7. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-054 settings and algorithm version

## Rollout Plan

### Step 1 — compute ratios at crawl time

- extract total_text_chars during crawl
- compute and cache content_ratio on each ContentItem
- verify ratios look sensible across the site

### Step 2 — diagnostics only

- implement FR-054 scoring with `ranking_weight = 0.0`
- verify that low-content-ratio pages are genuinely template-heavy

### Step 3 — operator review

- inspect pages with content_ratio < 0.30 to confirm they are genuinely thin
- confirm pages with content_ratio > 0.80 are genuinely content-rich

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.01` to `0.03`

## Risk List

- the `distilled_text` extractor may not perfectly separate content from chrome — mitigated by the conservative threshold and low starting weight;
- single-page applications (SPAs) may have very little visible text in the initial HTML — mitigated by the neutral fallback on pages with too few content characters;
- pages with legitimately minimal text (e.g., image galleries, video pages) will score low even though they may be good link destinations — operators should inspect these cases before enabling ranking impact;
- future work should implement proper DOM zone classification for higher accuracy.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"boilerplate_ratio.enabled": "true",
"boilerplate_ratio.ranking_weight": "0.02",
"boilerplate_ratio.boilerplate_threshold": "0.80",
"boilerplate_ratio.min_content_chars": "200",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.02` — conservative starting point. Boilerplate ratio is a structural quality signal, not a primary relevance signal. Raise to `0.04` after confirming ratios correlate with editorial quality.
- `boilerplate_threshold = 0.80` — pages with 80%+ content are considered healthy. Below this line, the signal ramps down linearly.
- `min_content_chars = 200` — pages with fewer than 200 characters of content are too short to score reliably.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- DOM-level zone classification (header/nav/main/aside/footer)
- cross-page template detection (identifying shared boilerplate across pages)
- JavaScript-rendered content analysis
- image-to-text ratio as a quality signal
- any dependency on analytics or telemetry data
- any modification to stored text or embeddings
