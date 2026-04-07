# FR-053 - Passage-Level Relevance Scoring

## Confirmation

- **Backlog confirmed**: `FR-053 - Passage-Level Relevance Scoring` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No passage-level or sub-document relevance signal exists in the current ranker. All existing relevance signals (`score_semantic`, `score_keyword`, `score_field_aware_relevance`) operate at full-document granularity. FR-053 scores the *best-matching passage* within the destination page — a fundamentally finer granularity.
- **Repo confirmed**: FAISS vector search and BGE-M3 embeddings are already established in the pipeline. FR-053 extends this infrastructure to passage-level embeddings without replacing it.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_semantic` — cosine similarity between host sentence embedding and *full destination page* embedding.
  - No signal currently scores at sub-document level within the destination.

- `backend/apps/pipeline/services/embeddings.py`
  - BGE-M3 embedding generation for full pages. FR-053 reuses the same model for passage embeddings.

- FAISS infrastructure
  - Already manages a per-site FAISS index of page-level embeddings.
  - FR-053 adds a separate passage-level FAISS index alongside the existing one.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Host sentence embedding is available per candidate.
  - Destination `ContentRecord` includes `distilled_text` for chunking into passages.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US9940367B1 — Scoring Candidate Answer Passages

**Plain-English description of the patent:**

The patent describes a passage-retrieval system that breaks documents into passages (roughly paragraph-sized chunks) and scores each passage independently against a query. Instead of comparing a query to the entire document, it finds the *best-matching passage* within the document and uses that passage's score as the document's relevance score. This captures cases where a long document has one highly relevant section buried among less relevant content.

**Repo-safe reading:**

The patent is oriented toward question-answering search. This repo adapts the idea to internal linking: a long destination page might have one paragraph that is perfectly relevant to the host sentence context, even if the page as a whole is only moderately similar. The reusable core idea is:

- chunk destination pages into fixed-size passages (~200 words each);
- compute a dense embedding for each passage;
- at suggestion time, find the best-matching passage and use its similarity as the score;
- this captures deep-page relevance that full-document scoring misses.

**What is directly supported by the patent:**

- chunking documents into passages for fine-grained scoring;
- using the best passage score as the document's relevance signal;
- embedding passages independently for dense retrieval.

**What is adapted for this repo:**

- "query" maps to the host sentence embedding, not a search query;
- passage embeddings use the same BGE-M3 model already in the pipeline;
- passage index is stored as a separate int8-quantized FAISS index to manage RAM;
- the signal is additive alongside full-document similarity, not a replacement for it.

## Plain-English Summary

Simple version first.

Imagine a long article with 10 sections. The page as a whole is about "guitar maintenance." But one section deep in the article is specifically about "cleaning rosewood fretboards." If the host sentence is about rosewood care, the full-document similarity score might be moderate — the page is broadly relevant but not a tight match. But the passage about rosewood fretboards is a near-perfect match.

FR-053 breaks each destination page into roughly paragraph-sized chunks (passages), embeds each passage separately, and at suggestion time finds the passage that is the best match for the host sentence. That best-passage score becomes the signal.

This is different from `score_semantic` because semantic similarity compares the host sentence to the *entire destination page embedding*. FR-053 compares the host sentence to the *best individual passage*. Long pages with one great section and nine average sections will score much higher under FR-053 than under `score_semantic`.

## Problem Statement

Today the ranker scores destination pages at full-document granularity. A 5000-word page with one perfect paragraph and nine mediocre paragraphs gets the same embedding as if the entire page were moderately relevant. The one perfect paragraph is "averaged away" in the page-level embedding.

This means the ranker systematically undervalues long pages with deep, section-specific relevance and overvalues short pages where the whole document matches (because there is nothing to average away).

FR-053 closes this gap by scoring at passage level and surfacing the best passage's similarity.

## Goals

FR-053 should:

- add a separate, explainable, bounded passage-level relevance signal;
- chunk destination pages into fixed-size passages at index time;
- embed each passage using the existing BGE-M3 model;
- store passage embeddings in a separate int8-quantized FAISS index;
- at suggestion time, find the best-matching passage via cosine similarity against the host sentence embedding;
- keep pages with too few words for passage chunking neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-053 does not:

- replace `score_semantic` — passage-level and document-level similarity are complementary;
- modify the existing page-level FAISS index;
- modify `ContentItem.distilled_text`, `ContentItem.title`, or the page-level embedding;
- change FR-006 through FR-052 logic;
- implement deep-linking (directing the reader to a specific section anchor) — that is a separate feature;
- use analytics, reviewer feedback, or any live query data;
- implement production code in the spec pass.

## Math-Fidelity Note

### Passage chunking (index time)

Let:

- `T` = `distilled_text` of a destination page
- `P` = `passage_words` setting (default 200 words)
- `K` = `passages_per_page` setting (default 5, maximum passages to store per page)

**Chunking procedure:**

```text
sentences = split_into_sentences(T)
passages = []
current_passage = []
current_word_count = 0

for sentence in sentences:
    w = word_count(sentence)
    if current_word_count + w > P and current_passage:
        passages.append(join(current_passage))
        current_passage = [sentence]
        current_word_count = w
    else:
        current_passage.append(sentence)
        current_word_count += w

if current_passage:
    passages.append(join(current_passage))

# Keep at most K passages (evenly spaced if more than K)
if len(passages) > K:
    indices = evenly_spaced_indices(len(passages), K)
    passages = [passages[i] for i in indices]
```

Chunking respects sentence boundaries — a passage is never split mid-sentence.

### Passage embedding (index time)

Each passage is embedded using the same BGE-M3 model:

```text
passage_embedding_i = bge_m3_encode(passage_i)
passage_embedding_i = passage_embedding_i / ||passage_embedding_i||_2
```

Embeddings are L2-normalized (unit vectors) so cosine similarity equals dot product.

For storage efficiency, passage embeddings are quantized to int8:

```text
int8_val = round((float_val - min_val) / (max_val - min_val) * 255) - 128
```

This reduces storage from 4096 bytes per embedding (1024 x float32) to 1024 bytes (1024 x int8).

### Signal definition (suggestion time)

Let:

- `q` = L2-normalized host sentence embedding (1024-dim float32)
- `p_1, p_2, ..., p_K` = passage embeddings for the destination page (dequantized to float32 at query time)

**Best-passage cosine similarity:**

```text
best_passage_sim = max( dot(q, p_i) for i in 1..K )
```

**Clamped similarity:**

```text
clamped_sim = max(0.0, min(1.0, best_passage_sim))
```

**Bounded score:**

```text
score_passage_relevance = 0.5 + 0.5 * clamped_sim
```

This maps:

- `best_passage_sim = 0.0` (no passage is similar to the host sentence) -> `score = 0.5` (neutral)
- `best_passage_sim = 1.0` (perfect passage match) -> `score = 1.0`
- Typical values sit in `[0.55, 0.85]` for real content pairs.

**Neutral fallback:**

```text
score_passage_relevance = 0.5
```

Used when:

- destination page has fewer than `passage_words` total words (too short to form a passage);
- passage embeddings are not available for this destination;
- feature is disabled.

### Why best-passage is the right aggregation

Mean-passage similarity would dilute a single excellent passage with many mediocre ones — the same problem as full-document scoring. Max-passage (best-passage) surfaces the strongest section match, which is exactly the signal we want: "somewhere in this destination, there is a section that deeply matches the host sentence."

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_passage_relevance_component =
  max(0.0, min(1.0, 2.0 * (score_passage_relevance - 0.5)))
```

```text
score_final += passage_relevance.ranking_weight * score_passage_relevance_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-053 must stay separate from:

- `score_semantic`
  - semantic measures host-sentence-to-full-destination-page similarity;
  - FR-053 measures host-sentence-to-best-destination-passage similarity;
  - different granularity, different embeddings (page-level vs passage-level), different aggregation.

- `score_keyword`
  - keyword measures token overlap at sentence-to-page level;
  - FR-053 measures dense embedding similarity at sentence-to-passage level;
  - different representation (sparse tokens vs dense embeddings), different scope.

- `score_field_aware_relevance` (FR-011)
  - FR-011 applies BM25 across destination title, body, scope, and anchor fields;
  - FR-053 applies cosine similarity across destination passages;
  - different scoring function (BM25 vs cosine), different decomposition (fields vs passages).

- `score_reference_context` (FR-051)
  - FR-051 measures the source insertion-point window;
  - FR-053 measures the destination passage;
  - opposite sides of the link (source context vs destination content).

Hard rule: FR-053 must not mutate any page-level embedding, token set, or text field used by any other signal.

## Inputs Required

FR-053 v1 needs:

- destination `distilled_text` — from `ContentRecord`, for chunking at index time
- BGE-M3 model — already loaded in the embedding pipeline, for passage embedding at index time
- host sentence embedding — already computed per candidate at suggestion time
- passage embeddings — stored in a separate FAISS index or PostgreSQL `pgvector` column

Explicitly disallowed FR-053 inputs in v1:

- page-level FAISS index (must not be modified)
- analytics or telemetry data
- any data not already available at pipeline time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `passage_relevance.enabled`
- `passage_relevance.ranking_weight`
- `passage_relevance.passages_per_page`
- `passage_relevance.passage_words`
- `passage_relevance.index_quantised`

Defaults:

- `enabled = true`
- `ranking_weight = 0.05`
- `passages_per_page = 5`
- `passage_words = 200`
- `index_quantised = true`

Bounds:

- `0.0 <= ranking_weight <= 0.15`
- `2 <= passages_per_page <= 10`
- `100 <= passage_words <= 500`

### Feature-flag behavior

- `enabled = false`
  - skip passage scoring entirely
  - store `score_passage_relevance = 0.5`
  - store `passage_relevance_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute passage scores and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.passage_relevance_diagnostics`

Required fields:

- `score_passage_relevance`
- `passage_relevance_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_destination_too_short`
  - `neutral_no_passages`
  - `neutral_processing_error`
- `best_passage_index` — which passage (0-indexed) scored highest
- `best_passage_similarity` — raw cosine similarity of the best passage
- `passage_count` — number of passages stored for this destination
- `all_passage_similarities` — list of cosine similarities for all passages (for operator inspection)
- `best_passage_preview` — first 100 characters of the best-matching passage text
- `passages_per_page_setting` — setting value used for this run
- `passage_words_setting` — setting value used for this run

Plain-English review helper text should say:

- `Passage relevance means a specific section of the destination page closely matches the host sentence.`
- `A high score means there is a paragraph in the destination that is directly about what the host sentence discusses.`
- `Neutral means the destination was too short for passage chunking, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_passage_relevance: FloatField(default=0.5)`
- `passage_relevance_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.passage_embeddings: JSONField(null=True, blank=True)` — stores passage metadata (count, word ranges)

A separate storage for the actual passage embedding vectors:

- Option A: separate FAISS index file per site (`passages.faiss`), alongside the existing `embeddings.faiss`
- Option B: `pgvector` column in a new `PassageEmbedding` model with FK to ContentItem

Recommended: Option A (FAISS), because it integrates with the existing FAISS infrastructure and supports int8 quantization natively via `faiss.IndexScalarQuantizer`.

### Estimated storage

- 100K pages x 5 passages x 1024 dims x 1 byte (int8) = ~500 MB
- With float32 (non-quantized): ~2 GB
- Quantization metadata (min/max per dimension): 8 KB

### PipelineRun snapshot

Add FR-053 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/passage-relevance/`
- `PUT /api/settings/passage-relevance/`

Add (for index management):

- `POST /api/settings/passage-relevance/rebuild-index/` — triggers re-chunking and re-embedding of all passages

### Review / admin / frontend

Add one new review row:

- `Passage Relevance`

Add one small diagnostics block:

- best passage similarity and passage index
- best passage text preview (first 100 chars)
- passage count for this destination
- all passage similarities (for operator deep-dive)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- passages per page input
- passage word count input
- quantization toggle

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/passage_relevance.py` — new service file (chunking, scoring)
- `backend/apps/pipeline/services/passage_indexer.py` — new service file (FAISS index management)
- `backend/apps/pipeline/services/ranker.py` — add FR-053 additive hook
- `backend/apps/pipeline/services/pipeline.py` — integrate passage scoring at suggestion time
- `backend/apps/pipeline/services/embeddings.py` — add passage embedding batch generation
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/content/models.py` — add passage metadata field
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-053 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoints
- `backend/apps/api/urls.py` — wire new settings endpoints
- `backend/apps/pipeline/tests.py` — FR-053 unit tests
- `backend/extensions/passagesim.cpp` — C++ extension for batch passage similarity
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-053 implementation pass:

- existing page-level FAISS index files
- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/rare_term_propagation.py`

## Test Plan

### 1. Passage chunking

- 1000-word page with `passage_words=200` produces 5 passages
- passages respect sentence boundaries — no mid-sentence splits
- page shorter than `passage_words` produces 1 passage (or triggers neutral fallback)
- `passages_per_page` cap is respected when page produces more passages than the limit

### 2. Best-passage similarity

- host sentence closely matches passage 3 of 5 -> `best_passage_index = 2`, high similarity
- host sentence matches no passage well -> low `best_passage_similarity`, score near 0.5
- single-passage destination behaves identically to full-document semantic (both use the whole text)

### 3. Neutral fallback cases

- destination has fewer than `passage_words` total words -> `score = 0.5`, state `neutral_destination_too_short`
- no passage embeddings available -> `score = 0.5`, state `neutral_no_passages`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in `[0.5, 1.0]` regardless of input
- `best_passage_similarity` is clamped to `[0.0, 1.0]`

### 6. Isolation from other signals

- changing `score_semantic` does not affect `score_passage_relevance`
- page-level FAISS index is never modified by FR-053
- passage embeddings are stored separately and never written to the page-level embedding

### 7. Quantization correctness

- int8 quantized passage embeddings produce similarity scores within 0.02 of float32 on a test set
- quantization metadata (min/max) is stored and loaded correctly

### 8. Serializer and frontend contract

- `score_passage_relevance` and `passage_relevance_diagnostics` appear in suggestion detail API response
- review dialog renders the `Passage Relevance` row
- settings page loads and saves FR-053 settings

### 9. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-053 settings and algorithm version

## Rollout Plan

### Step 1 — passage index build

- chunk and embed all destination pages
- build the passage FAISS index
- verify passage counts and embedding quality

### Step 2 — diagnostics only

- implement FR-053 scoring with `ranking_weight = 0.0`
- verify best-passage similarities look sensible
- confirm the int8 quantization does not degrade similarity quality

### Step 3 — operator review

- inspect `best_passage_preview` to confirm the best passage is genuinely the most relevant section
- compare `score_passage_relevance` against `score_semantic` for known good/bad pairs

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.06`

## Risk List

- passage chunking at sentence boundaries can produce uneven passage sizes — mitigated by the word-count target and the cap on passages per page;
- int8 quantization introduces ~1-2% cosine similarity error — acceptable for a ranking signal but should be validated on real data before enabling ranking impact;
- the passage FAISS index adds 250-500 MB of storage — significant but manageable within the 20 GB disk budget;
- passage re-embedding is required when `distilled_text` changes, adding ~5x the embedding computation cost vs page-level only — mitigated by incremental re-embedding only for changed pages;
- future work should not replace `score_semantic` with passage-level scoring — they are complementary axes (full-page topic match vs deep-section relevance).

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"passage_relevance.enabled": "true",
"passage_relevance.ranking_weight": "0.05",
"passage_relevance.passages_per_page": "5",
"passage_relevance.passage_words": "200",
"passage_relevance.index_quantised": "true",
```

**Why these values:**

- `enabled = true` — build passage index and run diagnostics from day one.
- `ranking_weight = 0.05` — moderate weight because passage similarity is a more precise version of semantic similarity. Worth more than micro-context (FR-051) but not enough to overpower full-doc semantic.
- `passages_per_page = 5` — balances granularity with storage. 5 passages cover most long pages without excessive index size.
- `passage_words = 200` — roughly paragraph-sized. Matches the patent's recommendation and produces meaningful embedding quality.
- `index_quantised = true` — int8 quantization keeps storage manageable.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- deep-linking to specific section anchors
- passage-level BM25 (keyword matching at passage level)
- dynamic passage sizing (variable-length based on topic boundaries)
- cross-passage context (using surrounding passages for richer embeddings)
- any dependency on analytics or telemetry data
- any modification to page-level embeddings or the existing FAISS index
