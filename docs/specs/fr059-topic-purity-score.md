# FR-059 - Topic Purity Score

## Confirmation

- **Backlog confirmed**: `FR-059 - Topic Purity Score` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No topic-purity or section-focus signal exists in the current ranker. The closest existing signal is topical authority cluster density (FR-048), which measures how tightly pages cluster in embedding space using HDBSCAN. FR-059 measures the *content-ratio purity* of a site section — what fraction of sentences within the section are actually on-topic versus off-topic — a fundamentally different axis. A tight embedding cluster can still contain off-topic digressions.
- **Repo confirmed**: Sentence-level embeddings and section/silo assignments are already available at pipeline time.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_silo_affinity` — prefers or penalizes cross-silo links, but does not measure the topical purity of the destination's section.
  - No signal currently measures how on-topic the content within a section actually is.

- `backend/apps/pipeline/services/embeddings.py`
  - BGE-M3 sentence-level embeddings are computed for all pages.
  - Section centroids can be derived by averaging page embeddings within a silo/section.

- Silo/section assignments
  - Pages are assigned to silos/sections via URL path structure or manual assignment.
  - Section membership is available at pipeline time.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Destination `ContentRecord` includes section assignment.
  - Sentence-level embeddings are available for cosine similarity computation.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US20210004416A1 — Extracting Key Phrase Candidates and Producing Topical Authority Ranking

**Plain-English description of the patent:**

The patent describes a system that evaluates the topical authority of website sections by extracting key phrases, computing topic distributions, and measuring how focused (pure) a section is on its core topic. Sections where most content aligns with the main topic rank as high-authority. Sections with scattered, off-topic content rank as low-authority, even if they contain some on-topic pages.

**Repo-safe reading:**

The patent uses key phrase extraction and topic modeling. This repo adapts the core idea using existing sentence embeddings and section centroids: for each section, compute the fraction of sentences whose embeddings are close to the section's centroid (on-topic) versus far from it (off-topic). The reusable core idea is:

- a focused section where 90% of sentences are on-topic is a stronger link destination than a scattered section where only 40% are on-topic;
- topic purity is measured by the fraction of sentences exceeding a cosine similarity threshold with the section centroid;
- higher purity = more authoritative, more predictable section for a reader.

**What is directly supported by the patent:**

- measuring the topical focus of site sections;
- using a purity/concentration ratio as a quality signal;
- treating focused sections as higher authority for linking purposes.

**What is adapted for this repo:**

- "key phrase extraction" is replaced by sentence embedding cosine similarity with the section centroid;
- "topic distribution" is replaced by a simple on-topic/off-topic binary classification per sentence;
- the signal is applied per-section and inherited by all pages within that section.

## Plain-English Summary

Simple version first.

Imagine a site section called "Guitar Maintenance." Most articles in the section are about cleaning, restringing, adjusting truss rods, and conditioning fretboards — all genuinely on-topic. But a few articles about "concert ticket prices" and "favorite guitar solos" ended up in the same section by accident. The section is not pure — it has off-topic noise.

FR-059 measures how focused each section is. It looks at every sentence in the section, checks whether each sentence is on-topic (close to the section's average content) or off-topic (far away), and computes the fraction that are on-topic.

A section where 95% of sentences are on-topic has high purity. A section where only 50% are on-topic has low purity. Linking into a high-purity section is better because the reader knows exactly what kind of content to expect.

This is different from topical authority cluster density (FR-048), which measures how tightly pages cluster in embedding space. FR-059 measures the content-ratio: what *fraction* of the content is on-topic. A tight cluster with contaminating off-topic pages still looks tight in embedding space but will have low purity.

## Problem Statement

Today the ranker can prefer same-silo links (silo affinity) and can measure cluster tightness (FR-048). But neither signal measures whether the destination's section is actually focused on its supposed topic.

This means a section with 10 on-topic pages and 5 completely off-topic pages looks the same as a section with 15 perfectly on-topic pages. The reader who follows a link into the mixed section may land on an on-topic page but then navigate to an off-topic neighbor — a confusing experience.

FR-059 closes this gap by scoring the topical purity of the destination page's section.

## Goals

FR-059 should:

- add a separate, explainable, bounded topic-purity signal;
- compute the on-topic sentence fraction for each section in the site;
- use cosine similarity between sentence embeddings and the section centroid;
- classify each sentence as on-topic (above threshold) or off-topic (below threshold);
- score destination pages by their section's purity;
- keep sections with too few sentences neutral at `0.5`;
- compute purity at index time (not at suggestion time) since it is a per-section property;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-059 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-058 logic;
- replace silo affinity or topical authority cluster density (FR-048) — they measure different things;
- implement topic modeling (LDA, BERTopic) — it uses cosine similarity with section centroids;
- use analytics, reviewer feedback, or any live query data;
- reassign pages to different sections — purity is a diagnostic, not a re-categorization tool;
- implement production code in the spec pass.

## Math-Fidelity Note

### Section centroid computation

Let:

- `S_k` = the set of pages in section `k`
- `e_i` = the L2-normalized embedding of page `i` (1024-dim float32)

**Section centroid:**

```text
centroid_k = mean(e_i for i in S_k)
centroid_k = centroid_k / ||centroid_k||_2
```

The centroid is the L2-normalized average embedding of all pages in the section.

### Sentence-level purity computation

Let:

- `sentences_k` = all sentences across all pages in section `k`
- `emb_j` = L2-normalized embedding of sentence `j`
- `theta` = `on_topic_threshold` setting (default 0.50)

**On-topic classification:**

```text
sim_j = dot(emb_j, centroid_k)

is_on_topic_j = 1 if sim_j >= theta else 0
```

**Purity ratio:**

```text
on_topic_count = sum(is_on_topic_j for j in sentences_k)
total_count = len(sentences_k)

purity_ratio = on_topic_count / max(total_count, 1)
```

This is the fraction of sentences in the section that are semantically aligned with the section's centroid.

- `purity_ratio = 0.95` — 95% of sentences are on-topic (highly focused section)
- `purity_ratio = 0.40` — 40% of sentences are on-topic (scattered section)
- `purity_ratio = 1.0` — every sentence is on-topic (perfect purity, rare)

### Signal definition

**Bounded score:**

```text
score_topic_purity = purity_ratio
```

The purity ratio is already naturally bounded in `[0, 1]` so no additional mapping is needed.

**Neutral fallback:**

```text
score_topic_purity = 0.5
```

Used when:

- section has fewer than `min_sentences` total sentences (default 5);
- page is not assigned to any section;
- sentence embeddings are unavailable;
- feature is disabled.

### Why sentence-level analysis is the right granularity

Page-level analysis would classify entire pages as on-topic or off-topic. But a page can be mostly on-topic with one off-topic paragraph. Sentence-level analysis captures this nuance and produces a smoother, more discriminative purity ratio. It also handles long pages that cover multiple sub-topics more accurately than a single page-level binary.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_topic_purity_component =
  max(0.0, min(1.0, 2.0 * (score_topic_purity - 0.5)))
```

```text
score_final += topic_purity.ranking_weight * score_topic_purity_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-059 must stay separate from:

- topical authority cluster density (FR-048)
  - FR-048 measures how tightly pages cluster in embedding space (geometric density);
  - FR-059 measures what fraction of sentence-level content is on-topic (content-ratio purity);
  - a dense cluster can still have low purity if it contains off-topic pages alongside on-topic ones;
  - different measurement: geometric tightness vs content composition.

- silo affinity
  - silo affinity prefers or penalizes cross-silo links (a binary direction preference);
  - FR-059 scores the quality of the section regardless of whether the link is same-silo or cross-silo;
  - a same-silo link into a low-purity section is worse than a cross-silo link into a high-purity section.

- `score_semantic`
  - semantic measures pair-level topical similarity;
  - FR-059 measures section-level topic focus;
  - different scope: pair vs section aggregate.

- `score_information_gain` (FR-038)
  - information gain measures vocabulary novelty;
  - FR-059 measures section focus;
  - independent axes.

Hard rule: FR-059 must not mutate any embedding, token set, text field, or section assignment used by any other signal.

## Inputs Required

FR-059 v1 needs:

- sentence-level embeddings — from the existing embedding pipeline (BGE-M3)
- section/silo assignments — from the existing page categorization
- section centroids — computed at index time from page embeddings within each section

Explicitly disallowed FR-059 inputs in v1:

- topic models (LDA, BERTopic)
- analytics or telemetry data
- manual section quality labels
- any data not available at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `topic_purity.enabled`
- `topic_purity.ranking_weight`
- `topic_purity.on_topic_threshold`
- `topic_purity.min_sentences`

Defaults:

- `enabled = true`
- `ranking_weight = 0.04`
- `on_topic_threshold = 0.50`
- `min_sentences = 5`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.20 <= on_topic_threshold <= 0.80`
- `3 <= min_sentences <= 50`

### Feature-flag behavior

- `enabled = false`
  - skip purity computation entirely
  - store `score_topic_purity = 0.5`
  - store `topic_purity_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute purity scores and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.topic_purity_diagnostics`

Required fields:

- `score_topic_purity`
- `topic_purity_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_section_too_small`
  - `neutral_no_section_assigned`
  - `neutral_embeddings_unavailable`
  - `neutral_processing_error`
- `section_name` — name/identifier of the destination's section
- `on_topic_count` — number of on-topic sentences in the section
- `total_sentence_count` — total sentences in the section
- `purity_ratio` — raw on-topic fraction
- `on_topic_threshold_setting` — threshold used for this computation
- `section_page_count` — number of pages in the section
- `sample_off_topic_sentences` — up to 3 example off-topic sentences for operator review (text preview, not full text)

Plain-English review helper text should say:

- `Topic purity means the destination page's section is focused on a clear topic rather than being a grab-bag of mixed content.`
- `A high score means the reader can expect consistently relevant content when exploring this section.`
- `Neutral means the section is too small to measure, the page has no section assignment, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_topic_purity: FloatField(default=0.5)`
- `topic_purity_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field needed per page.

Add a section-level cache (option: new model or JSON on existing Silo/Section model):

- `section_id` — FK or identifier
- `purity_ratio: FloatField`
- `on_topic_count: IntegerField`
- `total_sentence_count: IntegerField`
- `last_computed: DateTimeField`

Reason:

- purity is a per-section property, not per-page;
- all pages in the same section share the same purity score;
- caching avoids recomputing purity for every suggestion.

### PipelineRun snapshot

Add FR-059 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/topic-purity/`
- `PUT /api/settings/topic-purity/`
- `POST /api/settings/topic-purity/recompute/` — triggers re-computation of all section purity scores

### Review / admin / frontend

Add one new review row:

- `Topic Purity`

Add one small diagnostics block:

- section name and purity ratio
- on-topic count vs total sentence count
- sample off-topic sentences (up to 3)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- on-topic threshold input
- minimum sentences input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/topic_purity.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-059 additive hook
- `backend/apps/pipeline/services/pipeline.py` — read cached purity at suggestion time
- `backend/apps/pipeline/services/embeddings.py` — compute section centroids (read-only embedding use)
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-059 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoints
- `backend/apps/api/urls.py` — wire new settings endpoints
- `backend/apps/pipeline/tests.py` — FR-059 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-059 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`
- FR-048 topical authority cluster density — must remain independent

## Test Plan

### 1. Purity computation

- section with all sentences above threshold -> `purity_ratio = 1.0`, `score = 1.0`
- section with half above threshold -> `purity_ratio = 0.5`, `score = 0.5`
- section with no sentences above threshold -> `purity_ratio = 0.0`, `score = 0.0`

### 2. Section centroid

- centroid of a 3-page section is the normalized mean of the 3 page embeddings
- centroid is L2-normalized (unit vector)

### 3. Neutral fallback cases

- section has fewer than `min_sentences` -> `score = 0.5`, state `neutral_section_too_small`
- page not assigned to a section -> `score = 0.5`, state `neutral_no_section_assigned`
- embeddings unavailable -> `score = 0.5`, state `neutral_embeddings_unavailable`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in `[0.0, 1.0]` regardless of input

### 6. Isolation from other signals

- changing FR-048 cluster density does not affect `score_topic_purity`
- changing silo affinity does not affect `score_topic_purity`
- section centroids are computed read-only from existing embeddings — never modified

### 7. Serializer and frontend contract

- `score_topic_purity` and `topic_purity_diagnostics` appear in suggestion detail API response
- review dialog renders the `Topic Purity` row
- settings page loads and saves FR-059 settings

### 8. Sample sentence cap

- `sample_off_topic_sentences` contains at most 3 entries

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-059 settings and algorithm version

## Rollout Plan

### Step 1 — section centroid computation

- compute centroids for all sections from page embeddings
- verify centroids represent sensible section topics

### Step 2 — purity computation

- classify all sentences and compute purity ratios per section
- verify that high-purity sections are genuinely focused
- verify that low-purity sections contain identifiable off-topic content

### Step 3 — diagnostics only

- implement FR-059 scoring with `ranking_weight = 0.0`
- inspect `sample_off_topic_sentences` to confirm they are genuinely off-topic

### Step 4 — operator review

- confirm purity scores align with editorial assessment of section quality
- inspect edge cases (small sections, single-page sections)

### Step 5 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.05`

## Risk List

- the `on_topic_threshold` is sensitive — too high and everything is "off-topic," too low and everything is "on-topic." Mitigated by the operator-tunable threshold and the sample off-topic sentence diagnostics;
- section assignments may be inaccurate (pages in the wrong section inflate off-topic counts) — FR-059 surfaces this as diagnostic information, not a fix;
- very small sections (2-3 pages) produce noisy purity estimates — mitigated by the `min_sentences` threshold;
- sections that legitimately cover multiple related sub-topics will have lower purity even though they are editorially intentional — operators should inspect before enabling ranking impact;
- the centroid is pulled by all pages equally, including off-topic ones, which can dilute it. For heavily contaminated sections, iterative centroid refinement (excluding off-topic pages from the centroid) could improve accuracy — this is future work.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"topic_purity.enabled": "true",
"topic_purity.ranking_weight": "0.04",
"topic_purity.on_topic_threshold": "0.50",
"topic_purity.min_sentences": "5",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.04` — moderate weight. Topic purity is a strong structural quality signal but depends on accurate section assignments. Raise to `0.06` after confirming purity ratios align with editorial assessment.
- `on_topic_threshold = 0.50` — a cosine similarity of 0.5 is a reasonable boundary between on-topic and off-topic for BGE-M3 embeddings. Adjust based on the site's embedding distribution.
- `min_sentences = 5` — sections with fewer than 5 sentences are too small for meaningful purity measurement.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- topic modeling (LDA, BERTopic) for section topic identification
- automatic page reassignment based on purity analysis
- hierarchical purity (sub-section within section)
- cross-section purity comparison (ranking sections against each other)
- per-page purity contribution (which specific pages lower the section's score)
- any dependency on analytics or telemetry data
- any modification to stored text, embeddings, or section assignments
