# FR-039 - Entity Salience Match

## Confirmation

- **Backlog confirmed**: `FR-039 - Entity Salience Match` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No entity-salience signal exists in the current ranker. The closest existing signals are `score_semantic` (sentence-level embedding similarity) and `score_field_aware_relevance` (BM25 field weighting for destination fields). Neither measures whether the source page's *most important terms* are central to the destination.
- **Repo confirmed**: Site-wide document frequency computation is already established by FR-010's `rare_term_propagation.py`. FR-039 uses the same frequency map but for a different purpose and in the opposite direction.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - All existing signals measure how well the destination matches the host *sentence* or how authoritative the destination is in isolation.
  - No signal currently measures how prominent the *source page's* key topics are inside the destination page.

- `backend/apps/pipeline/services/rare_term_propagation.py` (FR-010)
  - Already computes site-wide document frequency for all normalized tokens.
  - FR-039 needs the same frequency map, built the same way, at the same time in the pipeline run.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns a normalized token set. Reused by FR-039 without modification.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Already loads `ContentRecord` rows for all destinations — includes normalized token sets.
  - Host page `ContentItem` (source page) is also accessible at pipeline time.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` snapshotting.

## Source Summary

### Patent: US9251473B2 — Identifying Salient Items in Documents

**Plain-English description of the patent:**

The patent describes a supervised machine learning system for identifying which named entities within a document are *salient* — meaning central and prominent — versus merely mentioned in passing. It uses signals including term frequency within the document, extra-document signals such as incoming anchor links, and user click data to calibrate entity importance.

**Repo-safe reading:**

The patent uses ML models and live user signals. This repo uses deterministic TF-IDF-style frequency arithmetic over the already-loaded corpus — simpler, reproducible, and dependency-free. The reusable core idea is:

- some terms are central to a page (salient) and others are incidental mentions;
- salience can be approximated by how often a term appears *within* the source page relative to how rarely it appears across the wider site;
- linking pages whose destination is *about* the source's salient topics is higher quality than linking pages that only incidentally mention those topics.

**What is directly supported by the patent:**

- using within-document term frequency and cross-document rarity to identify salient terms;
- using salient terms as a signal for relevance and link quality;
- treating salience as a document-level property rather than a sentence-level one.

**What is adapted for this repo:**

- "entity" maps to a salient normalized token rather than a named entity requiring NER;
- "extra-document signals" (anchor text, clicks) are replaced by site-wide document frequency from the already-loaded corpus;
- the signal is applied at suggestion time, not at search query time.

## Plain-English Summary

Simple version first.

Every page has a few words that really define what it is about — words it repeats often that most other pages do not use much.

For example, a page about a specific guitar model might repeat the model name many times. That model name barely appears anywhere else on the site. It is salient — it is what the source page is distinctly about.

FR-039 asks: does the destination page also prominently feature those defining words?

If yes — the destination is genuinely about the same core topic and is a strong link target.
If no — the destination may be topically adjacent but not truly aligned on the source's most important concepts.

This is different from `score_semantic`, which checks if the *host sentence* is relevant to the destination. FR-039 checks if the *whole source page's core topics* appear in the destination. These are different questions and can give different answers.

## Problem Statement

Today the ranker looks at the host sentence to decide if a destination is relevant. But the host sentence is just one small piece of the source page.

Two destination pages can score identically on `score_semantic` for the same host sentence, even when one destination is deeply focused on the source page's main topic and the other only mentions it as a side note.

FR-039 adds a signal that rewards destinations that are genuinely about the source page's core topics — not just destinations that match one well-placed sentence.

## Goals

FR-039 should:

- add a separate, explainable, bounded entity-salience-match signal;
- identify the source page's most salient terms using TF-IDF-style arithmetic over the loaded corpus;
- score how prominently those salient terms appear in the destination page;
- keep missing or insufficient data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-039 does not:

- use spaCy, NLTK, or any external NLP library for named entity recognition;
- require any new pip dependency;
- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-038 logic;
- use analytics, reviewer feedback, or any live query data;
- implement the ML salience model described in the patent — deterministic frequency arithmetic only;
- implement production code in the spec pass.

## Math-Fidelity Note

### Step 1 — build site-wide document frequency map (once per pipeline run)

Reuse the same map computed by FR-010. If FR-010 is disabled, FR-039 must compute it independently using the same logic.

```text
document_frequency(term) = number of non-deleted ContentItem pages
                           whose normalized token set contains term
```

### Step 2 — identify salient terms for the source page

Let:

- `source_tokens` = normalized token set of the source (host) page `distilled_text`, tokenized with `tokenize_text()`
- `source_tf(term)` = count of how many times `term` appears in the raw source page text (not deduplicated)
- `document_frequency(term)` = site-wide count from Step 1

A term is eligible to be salient only when all of the following hold:

1. it is in `source_tokens`
2. `source_tf(term) >= min_source_term_frequency` (default `2`) — must repeat within the source page
3. `document_frequency(term) <= max_site_document_frequency` (default `20`) — must be uncommon site-wide
4. token length >= `4` characters
5. it survives the existing stopword filter in `tokenize_text()`

**Salience weight per eligible term:**

```text
tf_component = min(1.0, source_tf(term) / 10.0)
idf_component = 1.0 - (document_frequency(term) / max(max_site_document_frequency, 1))
salience_weight(term) = 0.6 * tf_component + 0.4 * idf_component
```

**Top-N salient terms:**

- sort eligible terms by `salience_weight` descending
- keep the top `max_salient_terms` (default `10`)

Neutral fallback: if fewer than `2` eligible salient terms are found, the score is `0.5`.

### Step 3 — score how prominently salient terms appear in the destination

Let `dest_tokens` = normalized token set of the destination page `distilled_text`.

For each salient source term `t`:

```text
term_present(t) = 1 if t in dest_tokens else 0
```

**Match ratio:**

```text
match_ratio = sum(term_present(t) for t in salient_terms) / max(len(salient_terms), 1)
```

**Bounded score:**

```text
score_entity_salience_match = 0.5 + 0.5 * match_ratio
```

This maps:

- `match_ratio = 0.0` (none of the source's salient terms appear in destination) → `score = 0.5` (neutral)
- `match_ratio = 1.0` (all salient source terms appear in destination) → `score = 1.0`
- Typical values for strong matches sit in `[0.65, 0.85]`.

**Neutral fallback:**

```text
score_entity_salience_match = 0.5
```

Used when:

- source page has fewer than 2 eligible salient terms;
- source or destination page text is unavailable;
- feature is disabled.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_entity_salience_component =
  max(0.0, min(1.0, 2.0 * (score_entity_salience_match - 0.5)))
```

```text
score_final += entity_salience.ranking_weight * score_entity_salience_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact.

## Scope Boundary Versus Existing Signals

FR-039 must stay separate from:

- `score_semantic`
  - semantic compares *host sentence* embedding to *destination* embedding at sentence level;
  - FR-039 compares *source page body* salient terms to *destination body* tokens at document level;
  - different input scope, different computation.

- `score_keyword`
  - keyword uses Jaccard on *host sentence tokens* vs *destination tokens*;
  - FR-039 uses TF-IDF-weighted terms from the *source page body* matched against *destination tokens*;
  - different direction, different formula.

- `FR-010` rare-term propagation
  - FR-010 asks: "what rare terms from *nearby pages* does a *destination* share, to help it match a host sentence?"
  - FR-039 asks: "what *source page* salient terms appear in the *destination*?"
  - FR-010 runs in the *destination's* direction; FR-039 runs in the *source page's* direction.
  - They use the same document frequency map but for opposite purposes.

- `FR-011` field-aware relevance
  - FR-011 applies BM25 field weighting across destination title, body, scope, and anchor fields;
  - FR-039 does not apply field weighting and does not modify field-level scores.

Hard rule: FR-039 must not mutate any token set, embedding, or text field used by any other signal. FR-039 must not modify FR-010's term propagation data or document frequency cache.

## Inputs Required

FR-039 v1 can use only data already available in the pipeline:

- source (host) page `distilled_text` — raw text for TF counting + token set for frequency filtering
- destination `distilled_text` tokens — from `ContentRecord.tokens` already loaded per destination
- site-wide document frequency map — built once per pipeline run, reusable from FR-010 if available
- `tokenize_text(...)` — existing normalizer in `text_tokens.py`

Explicitly disallowed FR-039 inputs in v1:

- spaCy, NLTK, or any NER library
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

- `entity_salience.enabled`
- `entity_salience.ranking_weight`
- `entity_salience.max_salient_terms`
- `entity_salience.max_site_document_frequency`
- `entity_salience.min_source_term_frequency`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `max_salient_terms = 10`
- `max_site_document_frequency = 20`
- `min_source_term_frequency = 2`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `3 <= max_salient_terms <= 25`
- `5 <= max_site_document_frequency <= 100`
- `1 <= min_source_term_frequency <= 5`

### Feature-flag behavior

- `enabled = false`
  - skip all computation
  - store `score_entity_salience_match = 0.5`
  - store `entity_salience_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.entity_salience_diagnostics`

Required fields:

- `score_entity_salience_match`
- `entity_salience_state`
  - `computed_match`
  - `computed_no_match`
  - `neutral_feature_disabled`
  - `neutral_too_few_salient_terms`
  - `neutral_source_unavailable`
  - `neutral_destination_empty`
  - `neutral_processing_error`
- `salient_term_count` — number of eligible salient terms found in source page
- `matched_term_count` — how many appeared in the destination
- `match_ratio` — `matched / salient_term_count`
- `top_salient_terms` — up to 5 objects with `term`, `salience_weight`, `source_tf`, `document_frequency`, `present_in_destination`
- `max_salient_terms` — setting used in this run
- `max_site_document_frequency` — setting used in this run
- `min_source_term_frequency` — setting used in this run

Plain-English review helper text should say:

- `Entity salience means the destination page is built around the same core topics that define the source page.`
- `A high score means the destination prominently features the source page's most important and distinctive terms.`
- `Neutral means the source page did not have enough distinctive salient terms to compare, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_entity_salience_match: FloatField(default=0.5)`
- `entity_salience_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field needed.

Reason:

- entity salience match is suggestion-time and source-page-specific;
- the same destination scores differently depending on which source page is requesting the link.

### Separate tables

No new table required in v1.

Reason:

- the site-wide document frequency map is built in memory per pipeline run and is already computed by FR-010.
- source page salient terms are computed in memory per pipeline run, not persisted.

### PipelineRun snapshot

Add FR-039 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/entity-salience/`
- `PUT /api/settings/entity-salience/`

No recalculation endpoint in v1.

Reason:

- FR-039 is pair-specific and computed at suggestion time. There is no site-wide pre-computation step to trigger separately.

### Review / admin / frontend

Add one new review row:

- `Entity Salience Match`

Add one small diagnostics block:

- matched salient terms vs total salient terms
- top salient terms table (up to 5) showing term, whether present in destination, and salience weight
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- max salient terms
- max site document frequency
- min source term frequency

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/entity_salience.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-039 additive hook
- `backend/apps/pipeline/services/pipeline.py` — pass source page text and document frequency map to ranker context
- `backend/apps/pipeline/services/text_tokens.py` — reuse existing `tokenize_text()`
- `backend/apps/pipeline/services/rare_term_propagation.py` — read (do not modify) document frequency computation for reuse
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-039 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-039 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-039 implementation pass:

- `backend/apps/content/models.py` — no new content fields
- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/rare_term_propagation.py` — read-only reuse of document frequency logic; do not modify

## Test Plan

### 1. Salient term extraction

- a term appearing 3 times in source and rarely site-wide is eligible
- a term appearing 1 time in source is excluded when `min_source_term_frequency = 2`
- a term with site-wide `document_frequency > max_site_document_frequency` is excluded
- stopwords are excluded
- tokens under 4 characters are excluded
- salience weights are always in `[0.0, 1.0]`
- at most `max_salient_terms` terms are returned

### 2. Match scoring

- zero salient terms present in destination → `match_ratio = 0.0`, `score = 0.5`
- all salient terms present in destination → `match_ratio = 1.0`, `score = 1.0`
- partial match behaves proportionally

### 3. Neutral fallback cases

- source has fewer than 2 eligible salient terms → `score = 0.5`, state `neutral_too_few_salient_terms`
- source text unavailable → `score = 0.5`, state `neutral_source_unavailable`
- destination token set is empty → `score = 0.5`, state `neutral_destination_empty`
- feature disabled → `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` → final score ordering unchanged

### 5. Bounded score

- score is always in `[0.5, 1.0]` regardless of input
- no pair produces a score below `0.5` or above `1.0`

### 6. Isolation from FR-010

- FR-039 salience computation does not modify FR-010 rare-term profiles
- FR-039 document frequency map can be built independently if FR-010 is disabled
- changing FR-010 settings does not change FR-039 salient term selection

### 7. Isolation from other signals

- changing `score_semantic` inputs does not affect `score_entity_salience_match`
- salient terms are never written to `distilled_text`, embeddings, or any FR-008/FR-009 structure

### 8. Serializer and frontend contract

- `score_entity_salience_match` and `entity_salience_diagnostics` appear in suggestion detail API response
- review dialog renders the `Entity Salience Match` row
- settings page loads and saves FR-039 settings

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-039 settings and algorithm version

### 10. Top salient terms cap in diagnostics

- `top_salient_terms` in diagnostics contains at most 5 entries

## Rollout Plan

### Step 1 — diagnostics only

- implement FR-039 computation with `ranking_weight = 0.0`
- run a real pipeline and inspect `top_salient_terms` for a sample of source pages
- confirm the salient terms look like genuinely distinctive page topics, not noise

### Step 2 — operator review

- inspect matched vs unmatched salient terms for high-scoring and low-scoring suggestions
- verify that high-match destinations are genuinely on-topic for the source page's core subject
- verify that low-match (neutral) results make sense

### Step 3 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- short source pages may yield too few eligible salient terms, resulting in frequent neutral fallback — mitigated by the neutral-at-0.5 design;
- high `max_site_document_frequency` may let common terms through and dilute signal quality — inspect via diagnostics before raising this threshold;
- pages with broad topics (e.g. a general overview page) may have no strongly salient terms — this is correct behaviour; neutral is the right result;
- FR-010 and FR-039 share the same document frequency concept but serve opposite purposes — implementers must not conflate them; FR-010 identifies rare terms for destination-side enrichment, FR-039 identifies salient terms for source-side matching.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"entity_salience.enabled": "true",
"entity_salience.ranking_weight": "0.04",
"entity_salience.max_salient_terms": "10",
"entity_salience.max_site_document_frequency": "20",
"entity_salience.min_source_term_frequency": "2",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one so an operator can inspect `top_salient_terms` before enabling ranking impact.
- `ranking_weight = 0.04` — slightly more confident than FR-038 because TF-IDF-style entity salience is a well-established IR signal that is easy to inspect and reason about. Still conservative enough to act as a gentle boost rather than a dominant factor.
- `max_salient_terms = 10` — captures enough terms to represent the source page's topic without broadening to weak signals. Matches the spec default.
- `max_site_document_frequency = 20` — appropriate for a forum site where even specific product names or model numbers can appear on 10–15 pages. Allows moderately distinctive terms to qualify as salient without letting common vocabulary through.
- `min_source_term_frequency = 2` — requires a term to be repeated at least twice in the source page, filtering out incidental mentions. Matches the spec default.

### Migration note

The seeded preset in `migrations/0016_seed_recommended_preset.py` has already run on existing installs. FR-039 must ship a new data migration (or include a management command) that upserts these five keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

### `SETTING_TOOLTIPS` and `UI_TO_PRESET_KEY` entries (already added)

The frontend tooltip dictionary and the preset key map have both been pre-populated for:

- `entitySalience.enabled`
- `entitySalience.ranking_weight`
- `entitySalience.max_salient_terms`
- `entitySalience.max_site_document_frequency`
- `entitySalience.min_source_term_frequency`

The implementing developer only needs to wire these keys to the settings card UI fields — the tooltip text and preset mapping are already in place.

### `ALERT_THRESHOLDS` entries (already added)

- `entitySalience.ranking_weight`: warn above `0.08`, danger above `0.10`
- `entitySalience.max_salient_terms`: warn above `20`, danger above `24`
- `entitySalience.max_site_document_frequency`: warn above `60`, danger above `80`

## Out Of Scope

- named entity recognition (NER) using spaCy, NLTK, or any external library
- phrase-level salience (multi-token entity names)
- per-field salience weighting (title salience vs body salience)
- user-click or telemetry-based salience calibration (as in the original patent's ML approach)
- any modification to stored text, embeddings, or FR-010 propagated-term data
- any dependency on analytics or GSC data
