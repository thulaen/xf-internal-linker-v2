# FR-038 - Information Gain Scoring

## Confirmation

- **Backlog confirmed**: `FR-038 - Information Gain Scoring` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No information-gain signal exists in the current ranker. The closest existing signal is `score_keyword` (Jaccard similarity), which measures *overlap*. FR-038 measures *non-overlap from the destination's perspective* — a fundamentally different axis.
- **Repo confirmed**: Source page distilled text is already available at pipeline time. Destination tokens are already normalized by `text_tokens.py`.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_semantic` — sentence-level cosine similarity between host sentence embedding and destination embedding. Rewards *topical similarity*.
  - `score_keyword` — Jaccard similarity of host sentence tokens vs destination tokens. Also rewards *overlap*.
  - Neither signal measures whether the destination page *adds* information the source page does not already contain.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns a normalized token set. Already used by every ranking layer.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Loads `ContentRecord` rows for all destination candidates — includes `distilled_text` and normalized token sets.
  - The host page's own `distilled_text` is also accessible at pipeline-run time via the host `ContentItem`.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal (FR-008 through FR-015 pattern).
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern for algorithm version snapshotting.

## Source Summary

### Patent: US11354342B2 — Contextual Estimation of Link Information Gain

**Plain-English description of the patent:**

The patent describes scoring documents by how much *new* information they add beyond what a user has already seen. A document that repeats the same content as previously presented documents scores low. A document that introduces genuinely new information scores high.

**Repo-safe reading:**

The patent is search-engine oriented (measuring gain relative to a user's prior search session). This repo is suggestion-time and site-local. The reusable core idea is:

- measure what the destination adds that the source does not already say;
- treat high novelty as a positive signal, not a replacement for relevance;
- keep it additive and bounded on top of existing relevance scores.

**What is directly supported by the patent:**

- scoring documents by informational novelty relative to a known prior context;
- treating the source document as the "already seen" context;
- using the signal as an additive scoring layer.

**What is adapted for this repo:**

- "prior context" maps to the source (host) page's `distilled_text` tokens;
- "new document" maps to the destination `ContentItem`;
- the patent uses ML models over session context; this repo uses token set arithmetic over the loaded corpus — simpler, deterministic, and reproducible without a live model call.

## Plain-English Summary

Simple version first.

When a reader clicks an internal link, they get the most value when the destination page teaches them something they did not already read on the source page.

If the source page already covers the same ground as the destination, the link is low value — the reader already knows it.

FR-038 gives a bonus to destination pages that are genuinely *different* from the source page in content terms, while still being relevant (that is still handled by `score_semantic`).

Think of it this way: `score_semantic` asks "is the destination on the right topic?" FR-038 asks "does the destination actually add something new?"

## Problem Statement

Today the ranker rewards topical similarity and anchor quality. It does not directly reward informational novelty.

This means two equally relevant destinations are scored identically even when one is a near-duplicate of the source page in content terms. The reader would get more value from the destination that adds new information, but the ranker cannot tell the difference.

FR-038 closes this gap with a bounded, explainable, suggestion-level information gain signal.

## Goals

FR-038 should:

- add a separate, explainable, bounded information-gain signal;
- compute it from token-level set difference between the source page and the destination page;
- reward destination pages that add vocabulary and concepts the source page does not already contain;
- keep missing or insufficient source data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-038 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-037 logic;
- replace the relevance requirement — a high gain score does not override a low semantic score;
- use analytics, reviewer feedback, or any live query data;
- introduce a broad new indexing subsystem;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `S` = normalized token set of the source (host) page `distilled_text`
- `D` = normalized token set of the destination page `distilled_text`

**Novel destination tokens:**

```text
novel_tokens = D - S
```

(tokens in the destination that do not appear anywhere in the source page body)

**Raw gain ratio:**

```text
gain_ratio = len(novel_tokens) / max(len(D), 1)
```

This is the fraction of the destination's vocabulary that the source page does not already contain.

**Bounded score:**

```text
score_information_gain = 0.5 + 0.5 * gain_ratio
```

This maps:

- `gain_ratio = 0.0` (destination is a pure subset of source) → `score = 0.5` (neutral)
- `gain_ratio = 1.0` (destination shares no tokens with source) → `score = 1.0` (maximum gain)
- Typical values sit in `[0.65, 0.90]` for real content pairs.

**Neutral fallback:**

```text
score_information_gain = 0.5
```

Used when:

- source page text is missing or below `min_source_chars`;
- destination token set is empty;
- feature is disabled.

### Why this is the right formula

The Jaccard similarity used by `score_keyword` measures symmetric overlap:

```text
jaccard = len(S ∩ D) / max(len(S ∪ D), 1)
```

FR-038 measures *asymmetric novelty from the destination's perspective*:

```text
gain_ratio = len(D - S) / max(len(D), 1)
```

These are orthogonal. A pair can have high Jaccard (lots of shared terms, both pages cover the same ground) and low gain (destination adds little new). The two signals can and will disagree — which is exactly the useful signal.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_information_gain_component =
  max(0.0, min(1.0, 2.0 * (score_information_gain - 0.5)))
```

```text
score_final += information_gain.ranking_weight * score_information_gain_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-038 must stay separate from:

- `score_semantic`
  - semantic measures sentence-level embedding similarity (similarity);
  - FR-038 measures page-level token novelty (complementarity);
  - do not combine or average them.

- `score_keyword`
  - keyword uses Jaccard on *host sentence* vs *destination* tokens;
  - FR-038 uses set difference on *source page body* vs *destination body*;
  - different input scope, different formula, different axis.

- `FR-010` rare-term propagation
  - FR-010 borrows rare terms from *nearby related destination pages* to help one destination match a host sentence;
  - FR-038 measures what the *destination* adds that the *source page* does not already say;
  - completely different direction and purpose.

- `FR-011` field-aware relevance
  - FR-011 applies BM25 field weighting across title, body, scope, and anchor fields;
  - FR-038 does not apply field weighting and does not modify field-level scores.

Hard rule: FR-038 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-038 v1 can use only data already available in the pipeline:

- source (host) page `distilled_text` — from the host `ContentItem` already loaded at pipeline time
- destination `distilled_text` — from `ContentRecord.tokens` already loaded per destination
- `tokenize_text(...)` — existing normalizer in `text_tokens.py`

Explicitly disallowed FR-038 inputs in v1:

- inbound anchor text from `ExistingLink.anchor_text`
- embedding vectors
- analytics or telemetry data
- reviewer-edited anchors
- FR-007 history rows
- any data not already loaded by the pipeline at suggestion time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `information_gain.enabled`
- `information_gain.ranking_weight`
- `information_gain.min_source_chars`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `min_source_chars = 200`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `50 <= min_source_chars <= 1000`

### Feature-flag behavior

- `enabled = false`
  - skip gain computation entirely
  - store `score_information_gain = 0.5`
  - store `information_gain_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute gain and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.information_gain_diagnostics`

Required fields:

- `score_information_gain`
- `information_gain_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_source_too_short`
  - `neutral_destination_empty`
  - `neutral_processing_error`
- `source_token_count` — number of normalized tokens in source page body
- `destination_token_count` — number of normalized tokens in destination page body
- `novel_token_count` — count of destination tokens not found in source
- `gain_ratio` — raw `novel_token_count / destination_token_count`
- `sample_novel_tokens` — up to 5 example novel tokens for operator review (not the full set)
- `min_source_chars` — setting value used for this run

Plain-English review helper text should say:

- `Information gain means this destination page covers ground the source page does not already explain.`
- `A high score means the reader gets genuinely new content by following this link.`
- `Neutral means the source page text was too short to compare, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_information_gain: FloatField(default=0.5)`
- `information_gain_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field needed.

Reason:

- information gain is suggestion-time and pair-specific (source × destination), not a stable per-destination score;
- the same destination can have high gain relative to one source page and low gain relative to another.

### PipelineRun snapshot

Add FR-038 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/information-gain/`
- `PUT /api/settings/information-gain/`

No recalculation endpoint in v1.

Reason:

- FR-038 is pair-specific and computed at suggestion time. There is no site-wide pre-computation step to trigger.

### Review / admin / frontend

Add one new review row:

- `Information Gain`

Add one small diagnostics block:

- gain ratio
- novel token count vs destination token count
- sample novel tokens (up to 5)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- minimum source character threshold

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/information_gain.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-038 additive hook
- `backend/apps/pipeline/services/pipeline.py` — pass source page text to ranker context
- `backend/apps/pipeline/services/text_tokens.py` — reuse existing `tokenize_text()`
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-038 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-038 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-038 implementation pass:

- `backend/apps/content/models.py` — no new content fields
- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/rare_term_propagation.py`
- `backend/apps/pipeline/services/field_aware_relevance.py`

## Test Plan

### 1. Token set arithmetic

- destination is a pure subset of source → `gain_ratio = 0.0`, `score = 0.5`
- destination shares no tokens with source → `gain_ratio = 1.0`, `score = 1.0`
- partial overlap behaves proportionally

### 2. Neutral fallback cases

- source page `distilled_text` is shorter than `min_source_chars` → `score = 0.5`, state `neutral_source_too_short`
- destination token set is empty → `score = 0.5`, state `neutral_destination_empty`
- feature disabled → `score = 0.5`, state `neutral_feature_disabled`

### 3. Ranking off by default

- `ranking_weight = 0.0` → final score ordering unchanged

### 4. Bounded score

- score is always in `[0.5, 1.0]` regardless of input
- no pair produces a score below `0.5` or above `1.0`

### 5. Isolation from other signals

- changing `score_semantic` inputs does not affect `score_information_gain`
- changing FR-010 settings does not affect `score_information_gain`
- novel tokens are never written to `distilled_text`, embeddings, or any FR-008/FR-009 structure

### 6. Serializer and frontend contract

- `score_information_gain` and `information_gain_diagnostics` appear in suggestion detail API response
- review dialog renders the `Information Gain` row
- settings page loads and saves FR-038 settings

### 7. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-038 settings and algorithm version

### 8. Sample novel tokens cap

- `sample_novel_tokens` in diagnostics contains at most 5 entries regardless of `novel_token_count`

## Rollout Plan

### Step 1 — diagnostics only

- implement FR-038 computation with `ranking_weight = 0.0`
- verify gain ratios look sensible across a real pipeline run
- confirm neutral fallback is clean for short source pages

### Step 2 — operator review

- inspect whether `sample_novel_tokens` look like genuine new content vs noise
- confirm pairs with high gain are genuinely complementary pages, not unrelated ones
- confirm pairs with low gain are genuinely repetitive source-destination pairings

### Step 3 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- stopword-light tokenization may count many common tokens as "novel" on short pages, artificially inflating gain — mitigated by `min_source_chars` and the cap on sampling;
- very short destination pages score high gain trivially (their small vocabulary is unlikely to appear in the source) — inspect via diagnostics before enabling the weight;
- pages in the same silo naturally share vocabulary, so gain scores may be systematically lower for same-silo links — this is correct behaviour, not a bug;
- future work should not merge this signal with `score_keyword` or `score_semantic` — they must remain independent axes.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"information_gain.enabled": "true",
"information_gain.ranking_weight": "0.03",
"information_gain.min_source_chars": "200",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one so an operator can inspect `sample_novel_tokens` before enabling ranking impact.
- `ranking_weight = 0.03` — conservative starting point for an unvalidated signal. Acts as a light tie-breaker without overruling any established signal. Raise to `0.05` once a live pipeline run confirms the signal produces sensible novel token samples.
- `min_source_chars = 200` — ensures source pages have enough content for a meaningful comparison. Below ~200 characters the token set is too sparse to compute a reliable gain ratio.

### Migration note

The seeded preset in `migrations/0016_seed_recommended_preset.py` has already run on existing installs. FR-038 must ship a new data migration (or include a management command) that upserts these three keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

### `SETTING_TOOLTIPS` and `UI_TO_PRESET_KEY` entries (already added)

The frontend tooltip dictionary and the preset key map have both been pre-populated for:

- `informationGain.enabled`
- `informationGain.ranking_weight`
- `informationGain.min_source_chars`

The implementing developer only needs to wire these keys to the settings card UI fields — the tooltip text and preset mapping are already in place.

### `ALERT_THRESHOLDS` entries (already added)

- `informationGain.ranking_weight`: warn above `0.08`, danger above `0.10`
- `informationGain.min_source_chars`: warn below `80`, danger below `50`

## Out Of Scope

- phrase-level novelty detection
- embedding-space information gain (cosine dissimilarity)
- per-field novelty breakdown (title vs body)
- session-level or query-level information gain (as in the original patent)
- any modification to stored text or embeddings
- any dependency on analytics or telemetry data
