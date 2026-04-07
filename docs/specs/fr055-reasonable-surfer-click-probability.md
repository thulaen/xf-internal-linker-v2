# FR-055 - Reasonable Surfer Click Probability

## Confirmation

- **Backlog confirmed**: `FR-055 - Reasonable Surfer Click Probability` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No page-position or placement-quality signal exists in the current ranker. The closest existing signal is `score_click_distance` (FR-012), which measures graph hops between pages. FR-055 measures *where on the page* a link would appear and how likely a reader would notice and click it — a fundamentally different axis.
- **Repo confirmed**: The pipeline already knows the insertion point position within the host page body (sentence index, paragraph index). FR-055 extends this with zone classification and emphasis detection.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_click_distance` (FR-012) — measures graph hops between pages (structural proximity in the link graph).
  - No signal currently measures *on-page placement quality* — where on the source page the link would physically appear and how prominent that position is.

- `backend/apps/pipeline/services/pipeline.py`
  - Host sentence index and paragraph index are available per candidate at suggestion time.
  - The host page's structural zones (body, sidebar, header, footer) are not yet classified but can be derived from crawl data.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US8117209B1 — Ranking Documents Based on User Behavior and/or Feature Data

**Plain-English description of the patent:**

The patent describes the "Reasonable Surfer" model, which replaces the uniform random-surfer assumption in PageRank. Instead of treating all links on a page as equally likely to be clicked, it assigns different click probabilities based on observable features: the link's position on the page, which content zone it appears in (body vs. navigation vs. footer), the font size and emphasis of the anchor text, the surrounding content type, and the anchor text length.

**Repo-safe reading:**

The patent applies to web-scale link graph analysis. This repo adapts the core idea to internal link suggestion: when proposing where to insert a link, the placement quality matters. A link in the first body paragraph with bold anchor text is far more likely to be clicked than a link buried in a footer sidebar. The reusable core idea is:

- not all link positions are equally valuable;
- a link's click probability depends on its zone, position, emphasis, and anchor properties;
- higher click probability = higher link value.

**What is directly supported by the patent:**

- zone-based weighting (body > sidebar > header > footer);
- position-based decay (links higher on the page are more likely to be clicked);
- emphasis boost (bold, heading, larger font increases click probability);
- anchor text length as a feature (descriptive anchors are more clickable).

**What is adapted for this repo:**

- the patent models click probability for *existing* links; this repo models click probability for *proposed* link insertions;
- the patent uses observed click data to train weights; this repo uses fixed rule-based weights that can be tuned by operators;
- zone classification uses simple heuristics on page structure rather than ML models.

## Plain-English Summary

Simple version first.

Not all link positions on a page are equal. A link in the first paragraph of the main body content gets noticed by nearly every reader. A link buried at the bottom of a sidebar, after a long navigation menu, gets noticed by almost nobody.

FR-055 scores each proposed link insertion by how likely a "reasonable surfer" — an average reader casually browsing the page — would actually see and click it. The score depends on four things:

1. **Zone**: Is the link in the main body content, or in a sidebar/header/footer?
2. **Position**: Is the link near the top of the page or buried at the bottom?
3. **Emphasis**: Is the surrounding text bold, in a heading, or plain body text?
4. **Anchor length**: Is the anchor text descriptive (4+ words) or generic (1 word)?

A link in the body, near the top, in a heading, with a descriptive anchor scores highest. A link in the footer, at the bottom, in plain text, with a one-word anchor scores lowest.

This is different from `score_click_distance` (which measures graph hops between pages) and from `score_reference_context` (which measures topical relevance of the insertion window). FR-055 asks "would a reader actually see and click this link?"

## Problem Statement

Today the ranker determines *what* to link (relevance, authority, content quality) but not *where on the page* the link should go. All insertion points within the host page body are treated as equally valuable, even though a link in the first paragraph is dramatically more visible than a link near the bottom.

This means the ranker may propose links in low-visibility positions (deep in the page, in sidebar-like content, with short generic anchors) that technically score well on relevance but produce poor user engagement because readers never scroll down to see them.

FR-055 closes this gap by scoring each insertion point's click probability.

## Goals

FR-055 should:

- add a separate, explainable, bounded click-probability signal;
- score each insertion point by zone, position, emphasis, and anchor properties;
- use rule-based feature weights that operators can tune;
- keep placements with typical body-top positioning neutral or positive;
- keep missing zone/position data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-055 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-054 logic;
- use real click data or analytics — it uses structural heuristics only;
- implement ML-trained click probability models — it uses operator-tunable rule weights;
- replace relevance requirements — a high click probability does not override a low semantic score;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `z` = content zone of the insertion point: `body`, `sidebar`, `header`, or `footer`
- `w_z` = zone weight from settings (default: body=1.0, sidebar=0.5, header=0.3, footer=0.2)
- `n` = paragraph index of the insertion point within the zone (0-indexed from top)
- `N` = total paragraph count in the zone
- `e` = emphasis flag (1 if the sentence is in a heading, bold, or strong tag; 0 otherwise)
- `emphasis_boost` = emphasis multiplier from settings (default 1.2)
- `a` = anchor text word count of the proposed link

**Position decay (higher = closer to top):**

```text
position_score = 1.0 - (n / max(N, 1)) * 0.5
```

This maps:

- first paragraph (`n=0`) -> `position_score = 1.0`
- middle of the zone -> `position_score = 0.75`
- last paragraph -> `position_score = 0.50`

The 0.5 floor ensures even bottom-of-page links get some credit.

**Anchor length factor:**

```text
anchor_factor = min(1.0, a / 4.0)
```

This maps:

- 1-word anchor -> `anchor_factor = 0.25`
- 2-word anchor -> `anchor_factor = 0.50`
- 4+ word anchor -> `anchor_factor = 1.00`

**Emphasis multiplier:**

```text
emphasis_multiplier = emphasis_boost if e == 1 else 1.0
```

**Raw click probability (unnormalized):**

```text
raw_click_prob = w_z * position_score * anchor_factor * emphasis_multiplier
```

**Bounded score:**

```text
score_reasonable_surfer = 0.5 + 0.5 * min(1.0, raw_click_prob / max_possible_prob)
```

where `max_possible_prob = w_body * 1.0 * 1.0 * emphasis_boost` (the theoretical maximum: body zone, top position, 4+ word anchor, emphasized).

This maps:

- best possible placement -> `score = 1.0`
- typical body-middle placement with 3-word anchor -> `score ~ 0.70`
- footer placement with 1-word anchor -> `score ~ 0.53`

**Neutral fallback:**

```text
score_reasonable_surfer = 0.5
```

Used when:

- zone classification is unavailable;
- paragraph index is unavailable;
- feature is disabled.

### Why multiplicative combination is the right approach

Zone, position, emphasis, and anchor length are independent features that compound. A body link (good zone) near the bottom (bad position) should score less than a body link near the top. Multiplication naturally handles this: each factor scales the probability independently, and the product reflects their joint effect.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_reasonable_surfer_component =
  max(0.0, min(1.0, 2.0 * (score_reasonable_surfer - 0.5)))
```

```text
score_final += reasonable_surfer.ranking_weight * score_reasonable_surfer_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-055 must stay separate from:

- `score_click_distance` (FR-012)
  - click distance measures graph hops between pages (inter-page structural proximity);
  - FR-055 measures on-page placement quality (intra-page position);
  - completely different scope: between pages vs within a page.

- `score_reference_context` (FR-051)
  - reference context measures the topical relevance of the insertion window;
  - FR-055 measures the visibility and click probability of the insertion position;
  - one is about content, the other is about placement.

- `score_semantic`
  - semantic measures topical similarity;
  - FR-055 measures position quality;
  - orthogonal axes.

- `score_phrase_match` (FR-008)
  - phrase matching scores anchor text quality;
  - FR-055 uses anchor length as one sub-feature but also includes zone, position, and emphasis;
  - FR-055 is broader in scope and different in purpose.

Hard rule: FR-055 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-055 v1 needs:

- insertion point zone classification — derived from page structure (body/sidebar/header/footer)
- insertion point paragraph index — from the pipeline's sentence/paragraph metadata
- emphasis flag — whether the insertion sentence is in a heading, bold, or strong context
- anchor text word count — from the proposed anchor text

Explicitly disallowed FR-055 inputs in v1:

- real click data or analytics (FR-055 is structure-based, not behavior-based)
- embedding vectors
- any data not available from page structure and suggestion metadata

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `reasonable_surfer.enabled`
- `reasonable_surfer.ranking_weight`
- `reasonable_surfer.zone_weight_body`
- `reasonable_surfer.zone_weight_sidebar`
- `reasonable_surfer.zone_weight_header`
- `reasonable_surfer.zone_weight_footer`
- `reasonable_surfer.emphasis_boost`

Defaults:

- `enabled = true`
- `ranking_weight = 0.03`
- `zone_weight_body = 1.0`
- `zone_weight_sidebar = 0.5`
- `zone_weight_header = 0.3`
- `zone_weight_footer = 0.2`
- `emphasis_boost = 1.2`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.0 <= zone_weight_* <= 1.0`
- `1.0 <= emphasis_boost <= 2.0`

### Feature-flag behavior

- `enabled = false`
  - skip click probability computation entirely
  - store `score_reasonable_surfer = 0.5`
  - store `reasonable_surfer_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute click probabilities and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.reasonable_surfer_diagnostics`

Required fields:

- `score_reasonable_surfer`
- `reasonable_surfer_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_zone_unavailable`
  - `neutral_position_unavailable`
  - `neutral_processing_error`
- `zone` — classified zone (body/sidebar/header/footer)
- `zone_weight` — weight applied for this zone
- `paragraph_index` — 0-indexed position within the zone
- `total_paragraphs` — total paragraph count in the zone
- `position_score` — position decay value
- `anchor_word_count` — word count of the proposed anchor
- `anchor_factor` — anchor length factor applied
- `emphasis_detected` — whether emphasis was detected (true/false)
- `emphasis_multiplier` — multiplier applied
- `raw_click_prob` — pre-normalization click probability

Plain-English review helper text should say:

- `Reasonable surfer means this link is placed where a typical reader would actually see and click it.`
- `A high score means the link is in a prominent position with descriptive anchor text.`
- `Neutral means zone or position data was unavailable, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_reasonable_surfer: FloatField(default=0.5)`
- `reasonable_surfer_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field needed.

Reason:

- click probability is position-specific and suggestion-specific, not a per-page property;
- the same page can have high-value insertion points (top of body) and low-value ones (footer).

### PipelineRun snapshot

Add FR-055 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/reasonable-surfer/`
- `PUT /api/settings/reasonable-surfer/`

No recalculation endpoint in v1.

### Review / admin / frontend

Add one new review row:

- `Reasonable Surfer`

Add one small diagnostics block:

- zone and zone weight
- paragraph position (n of N)
- anchor factor and emphasis flag
- raw click probability
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- zone weight inputs (body, sidebar, header, footer)
- emphasis boost input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/reasonable_surfer.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-055 additive hook
- `backend/apps/pipeline/services/pipeline.py` — pass zone, position, emphasis metadata to ranker
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-055 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-055 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-055 implementation pass:

- `backend/apps/content/models.py` — no new content fields
- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`

## Test Plan

### 1. Zone-based scoring

- body zone, top position, 4-word anchor, emphasized -> score near 1.0
- footer zone, bottom position, 1-word anchor, no emphasis -> score near 0.52
- sidebar zone, mid position -> intermediate score

### 2. Position decay

- first paragraph -> `position_score = 1.0`
- last paragraph of 20 -> `position_score = 0.525`
- position_score never drops below 0.5

### 3. Anchor length factor

- 1-word anchor -> `anchor_factor = 0.25`
- 4-word anchor -> `anchor_factor = 1.0`
- 10-word anchor -> `anchor_factor = 1.0` (capped at 1.0)

### 4. Neutral fallback cases

- zone classification unavailable -> `score = 0.5`, state `neutral_zone_unavailable`
- paragraph index unavailable -> `score = 0.5`, state `neutral_position_unavailable`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 5. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 6. Bounded score

- score is always in `[0.5, 1.0]` regardless of input

### 7. Isolation from other signals

- changing `score_click_distance` does not affect `score_reasonable_surfer`
- changing `score_reference_context` does not affect `score_reasonable_surfer`

### 8. Serializer and frontend contract

- `score_reasonable_surfer` and `reasonable_surfer_diagnostics` appear in suggestion detail API response
- review dialog renders the `Reasonable Surfer` row
- settings page loads and saves FR-055 settings

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-055 settings and algorithm version

## Rollout Plan

### Step 1 — zone classification

- implement zone detection from page structure
- verify zone assignments look correct across a sample of pages

### Step 2 — diagnostics only

- implement FR-055 scoring with `ranking_weight = 0.0`
- verify click probabilities correlate with intuitive placement quality

### Step 3 — operator review

- inspect high-scoring placements (should be body, top, emphasized, descriptive anchor)
- inspect low-scoring placements (should be footer/sidebar, bottom, generic anchor)

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- zone classification from HTML structure may be inaccurate for unconventional page layouts — mitigated by the neutral fallback and conservative starting weight;
- emphasis detection depends on HTML markup (strong, b, h1-h6) which may vary across CMS templates — mitigated by treating emphasis as a bonus multiplier (missing it just means no boost, not a penalty);
- the model is rule-based, not data-driven — it cannot adapt to site-specific reader behavior. Future work could incorporate actual click data to calibrate weights;
- anchor word count does not capture anchor quality (a 4-word anchor like "click here now please" is long but bad) — FR-008 phrase matching handles anchor quality separately.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"reasonable_surfer.enabled": "true",
"reasonable_surfer.ranking_weight": "0.03",
"reasonable_surfer.zone_weight_body": "1.0",
"reasonable_surfer.zone_weight_sidebar": "0.5",
"reasonable_surfer.zone_weight_header": "0.3",
"reasonable_surfer.zone_weight_footer": "0.2",
"reasonable_surfer.emphasis_boost": "1.2",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.03` — moderate starting weight. Placement quality is important but should not overpower relevance signals.
- zone weights follow a natural reading attention gradient: body > sidebar > header > footer.
- `emphasis_boost = 1.2` — a 20% bonus for emphasized text. Conservative enough to avoid over-rewarding heading placement.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- real click-through rate data integration
- ML-trained click probability models
- eye-tracking-based attention models
- above-the-fold vs below-the-fold viewport analysis
- mobile vs desktop position differences
- any dependency on analytics or telemetry data
- any modification to stored text or embeddings
