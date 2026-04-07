# FR-052 - Readability Level Matching

## Confirmation

- **Backlog confirmed**: `FR-052 - Readability Level Matching` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No readability or reading-complexity signal exists in the current ranker. The closest existing signals are `score_semantic` (topical similarity) and `score_field_aware_relevance` (BM25 keyword relevance). Neither measures how *difficult* the text is to read.
- **Repo confirmed**: Source and destination `distilled_text` are already available at pipeline time. Word and sentence counts can be derived from existing text with no new data source.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - All existing signals measure topical relevance, structural position, or content quality — none measure reading difficulty.
  - No signal currently compares the *reading level* of the source page to the destination page.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns a normalized token set. FR-052 needs raw text (not tokenized) because syllable counting operates on original word forms.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Host page `ContentItem` with `distilled_text` is available at pipeline time.
  - Destination `ContentRecord` rows include `distilled_text`.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US20070067294A1 — Readability and Context Identification and Exploitation

**Plain-English description of the patent:**

The patent describes a system that computes the reading difficulty level of web documents and uses that information to match content to readers. Documents are scored using standard readability formulas (Flesch-Kincaid, Gunning Fog, etc.) and the scores are used to filter or rank results so that a reader gets content at an appropriate difficulty level.

**Repo-safe reading:**

The patent applies readability to search result ranking for users of known reading levels. This repo adapts the idea to internal linking: when a source page is written at grade 8, linking to a destination written at grade 16 creates a jarring difficulty jump for the reader. The reusable core idea is:

- compute a standardized readability grade for each page;
- penalize links where source and destination differ sharply in reading level;
- treat similar reading levels as a quality signal for link coherence.

**What is directly supported by the patent:**

- using Flesch-Kincaid grade level as the readability metric;
- scoring documents by reading difficulty;
- using reading level as a ranking factor for content matching.

**What is adapted for this repo:**

- instead of matching content to a user's reading level, FR-052 matches source-page reading level to destination-page reading level;
- the patent uses readability for filtering; this repo uses it as a soft penalty signal;
- grade level is computed from `distilled_text` rather than raw HTML.

## Plain-English Summary

Simple version first.

Every page has a reading difficulty level. A blog post written with short sentences and common words might be at grade 6. A technical whitepaper with jargon and long sentences might be at grade 14.

When a grade-6 blog post links to a grade-14 whitepaper, the reader experiences a jarring jump. They clicked expecting more of the same easy reading, but landed on dense academic text. That is a bad experience.

FR-052 measures the reading level of both the source page and the destination page using the Flesch-Kincaid formula (a standard formula that counts syllables, words, and sentences). If the grade levels are close (within 3 grades), the link is fine. If they are far apart, FR-052 applies a soft penalty.

This is different from every other signal in the ranker. Semantic similarity asks "is it on the right topic?" Phrase matching asks "do the words match?" FR-052 asks "is the destination written at a similar difficulty level?" A destination can be perfectly on-topic but still be a bad link if the reader cannot comfortably read it.

## Problem Statement

Today the ranker rewards topical relevance, keyword overlap, authority, and structural quality. It does not consider whether the destination page is written at a reading level appropriate for someone reading the source page.

This means a casual how-to guide (grade 7) can link to a dense specification document (grade 15) with no penalty, even though the reader who clicked from the guide is unlikely to find the specification accessible. Conversely, an advanced technical page linking to an oversimplified primer wastes the reader's time.

FR-052 closes this gap with a bounded readability-distance penalty.

## Goals

FR-052 should:

- add a separate, explainable, bounded readability-match signal;
- compute Flesch-Kincaid grade level for both source and destination pages;
- apply a soft penalty proportional to the grade-level difference when it exceeds `max_grade_gap`;
- keep pages with similar reading levels neutral (no penalty, no boost);
- keep missing or insufficient text neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- require zero external dependencies — pure formula on word, sentence, and syllable counts;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-052 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-051 logic;
- replace the relevance requirement — a good readability match does not override a low semantic score;
- use analytics, reviewer feedback, or any live query data;
- implement NLP models or ML-based readability predictors — it uses the deterministic Flesch-Kincaid formula;
- implement production code in the spec pass.

## Math-Fidelity Note

### Flesch-Kincaid grade level

Let:

- `W` = total word count of the page `distilled_text`
- `S` = total sentence count (sentences detected by terminal punctuation: `.`, `?`, `!`)
- `Y` = total syllable count across all words

**Flesch-Kincaid Grade Level (FKGL):**

```text
FKGL = 0.39 * (W / S) + 11.8 * (Y / W) - 15.59
```

This produces a US school grade level. Grade 5 = fifth grader can read it. Grade 12 = high school senior. Grade 16+ = college graduate level.

**Clamping:**

```text
FKGL_clamped = max(1.0, min(20.0, FKGL))
```

Scores below 1 or above 20 are meaningless artifacts of very short or very unusual text.

### Syllable counting heuristic

For English text, syllables are estimated by:

1. Count vowel groups (sequences of `a, e, i, o, u, y`) in each word.
2. Subtract 1 for a trailing silent `e` (if word length > 2 and ends in `e` and second-to-last letter is not a vowel).
3. Floor at 1 syllable per word.

This is a well-known heuristic used by the original Flesch-Kincaid implementations. It is accurate to within ~5% for English text.

### Signal definition

Let:

- `G_src` = `FKGL_clamped` of the source (host) page
- `G_dst` = `FKGL_clamped` of the destination page
- `max_grade_gap` = the maximum acceptable grade difference before penalty begins (default 3)
- `penalty_per_grade` = penalty subtracted per grade level beyond the gap (default 0.10)

**Grade distance:**

```text
grade_distance = abs(G_src - G_dst)
```

**Excess distance (beyond the allowed gap):**

```text
excess = max(0.0, grade_distance - max_grade_gap)
```

**Raw penalty:**

```text
raw_penalty = excess * penalty_per_grade
```

**Bounded score:**

```text
score_readability_match = max(0.0, min(1.0, 1.0 - raw_penalty))
```

This maps:

- `grade_distance <= max_grade_gap` (e.g., within 3 grades) -> `score = 1.0` (no penalty)
- `grade_distance = max_grade_gap + 5` (e.g., 8 grades apart) -> `score = 1.0 - 5 * 0.10 = 0.50`
- `grade_distance = max_grade_gap + 10` (e.g., 13 grades apart) -> `score = max(0.0, 1.0 - 10 * 0.10) = 0.0`

**Neutral fallback:**

```text
score_readability_match = 0.5
```

Used when:

- source or destination `distilled_text` has fewer than 100 words (too short for reliable FKGL);
- sentence count is zero (cannot compute FKGL);
- feature is disabled.

### Why Flesch-Kincaid is the right formula

Flesch-Kincaid is deterministic, language-independent in principle (calibrated for English), requires no external model or API, and has been the standard readability metric in education, government, and publishing for decades. It uses only three counts (words, sentences, syllables) that are trivially computable from `distilled_text`. More sophisticated models (Dale-Chall, Coleman-Liau) add marginal accuracy at much higher implementation cost.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_readability_match_component =
  max(0.0, min(1.0, 2.0 * (score_readability_match - 0.5)))
```

```text
score_final += readability_match.ranking_weight * score_readability_match_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-052 must stay separate from:

- `score_semantic`
  - semantic measures topical similarity via dense embeddings;
  - FR-052 measures reading difficulty distance via syllable/word/sentence statistics;
  - completely different input features and axis.

- `score_keyword`
  - keyword measures token overlap (Jaccard similarity);
  - FR-052 measures text complexity — two pages can share zero keywords but have identical reading levels;
  - orthogonal axes.

- `score_information_gain` (FR-038)
  - information gain measures vocabulary novelty between source and destination;
  - FR-052 measures writing complexity — a highly novel destination can be at the same reading level;
  - independent signals.

- `score_fact_density` (FR-042)
  - fact density measures the proportion of factual claims in the text;
  - FR-052 measures how hard those sentences are to read, regardless of whether they are factual;
  - a page can be fact-dense and easy to read, or fact-sparse and hard to read.

Hard rule: FR-052 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-052 v1 can use only data already available in the pipeline:

- source (host) page `distilled_text` — from the host `ContentItem`
- destination `distilled_text` — from `ContentRecord` already loaded per destination
- word, sentence, and syllable counts — derived from `distilled_text` at computation time

Explicitly disallowed FR-052 inputs in v1:

- raw HTML (readability is computed from distilled text, not markup)
- embedding vectors
- analytics or telemetry data
- any data not already loaded by the pipeline at suggestion time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `readability_match.enabled`
- `readability_match.ranking_weight`
- `readability_match.max_grade_gap`
- `readability_match.penalty_per_grade`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `max_grade_gap = 3`
- `penalty_per_grade = 0.10`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1 <= max_grade_gap <= 10`
- `0.01 <= penalty_per_grade <= 0.30`

### Feature-flag behavior

- `enabled = false`
  - skip readability computation entirely
  - store `score_readability_match = 0.5`
  - store `readability_match_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute readability scores and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.readability_match_diagnostics`

Required fields:

- `score_readability_match`
- `readability_match_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_source_too_short`
  - `neutral_destination_too_short`
  - `neutral_no_sentences`
  - `neutral_processing_error`
- `source_fkgl` — Flesch-Kincaid grade level of the source page
- `destination_fkgl` — Flesch-Kincaid grade level of the destination page
- `grade_distance` — absolute difference between the two
- `excess` — how many grades beyond `max_grade_gap`
- `source_word_count` — word count used for source FKGL computation
- `source_sentence_count` — sentence count used for source FKGL computation
- `destination_word_count` — word count used for destination FKGL computation
- `destination_sentence_count` — sentence count used for destination FKGL computation
- `max_grade_gap_setting` — setting value used for this run
- `penalty_per_grade_setting` — setting value used for this run

Plain-English review helper text should say:

- `Readability match means the source and destination pages are written at similar difficulty levels.`
- `A high score means the reader will not experience a jarring difficulty jump when following this link.`
- `Neutral means one or both pages had too little text for a reliable reading level estimate, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_readability_match: FloatField(default=0.5)`
- `readability_match_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.readability_grade: FloatField(null=True, blank=True)`

Reason:

- unlike most FR-051+ signals which are pair-specific, Flesch-Kincaid grade is a stable per-page property;
- computing it once per page and caching it avoids redundant recalculation across all suggestions referencing that page;
- the cached value is invalidated and recomputed when `distilled_text` changes.

### PipelineRun snapshot

Add FR-052 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/readability-match/`
- `PUT /api/settings/readability-match/`

No recalculation endpoint in v1.

### Review / admin / frontend

Add one new review row:

- `Readability Match`

Add one small diagnostics block:

- source FKGL grade and destination FKGL grade
- grade distance and excess
- penalty applied
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- maximum grade gap input
- penalty per grade input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/readability.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-052 additive hook
- `backend/apps/pipeline/services/pipeline.py` — compute readability grades for source and destinations
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/content/models.py` — add `readability_grade` field on ContentItem
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-052 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-052 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-052 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/rare_term_propagation.py`
- `backend/apps/pipeline/services/information_gain.py`
- `backend/apps/pipeline/services/reference_context.py`

## Test Plan

### 1. Flesch-Kincaid computation

- known text sample at grade 5 produces FKGL near 5.0
- known text sample at grade 12 produces FKGL near 12.0
- very short text (1 sentence) still produces a valid clamped grade
- empty text returns None (triggers neutral fallback)

### 2. Grade distance scoring

- same reading level -> `score = 1.0`
- within `max_grade_gap` (e.g., 2 grades apart, gap = 3) -> `score = 1.0`
- exceeds gap by 3 grades -> `score = 1.0 - 3 * 0.10 = 0.70`
- exceeds gap by 10 grades -> `score = max(0.0, 1.0 - 10 * 0.10) = 0.0`

### 3. Neutral fallback cases

- source has fewer than 100 words -> `score = 0.5`, state `neutral_source_too_short`
- destination has fewer than 100 words -> `score = 0.5`, state `neutral_destination_too_short`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in `[0.0, 1.0]` regardless of input
- FKGL is always in `[1.0, 20.0]` after clamping

### 6. Isolation from other signals

- changing `score_semantic` inputs does not affect `score_readability_match`
- changing FR-042 fact density does not affect `score_readability_match`
- readability grade is stored on ContentItem but never modifies `distilled_text` or embeddings

### 7. Serializer and frontend contract

- `score_readability_match` and `readability_match_diagnostics` appear in suggestion detail API response
- review dialog renders the `Readability Match` row
- settings page loads and saves FR-052 settings

### 8. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-052 settings and algorithm version

## Rollout Plan

### Step 1 — diagnostics only

- implement FR-052 computation with `ranking_weight = 0.0`
- verify FKGL grades look reasonable across the site's content
- confirm penalty behavior on known easy/hard page pairs

### Step 2 — operator review

- inspect source and destination FKGL grades for edge cases (very short pages, non-English content)
- confirm that high-penalty pairs are genuinely jarring difficulty jumps
- confirm that low-penalty pairs are genuinely similar in reading level

### Step 3 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.01` to `0.03`

## Risk List

- Flesch-Kincaid is calibrated for English prose. Non-English content or technical jargon (code snippets, product names) may produce unreliable grades — mitigated by the neutral fallback on short text and the conservative starting weight;
- very short pages (<100 words) produce noisy FKGL estimates — mitigated by the minimum word threshold that triggers neutral fallback;
- pages that mix difficulty levels (e.g., a simple intro followed by a dense technical section) get a single averaged grade that may not reflect the reader's actual experience — future work could segment by section;
- the syllable heuristic is approximate (~5% error) — this is acceptable for a ranking signal but should not be displayed to operators as an exact value.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"readability_match.enabled": "true",
"readability_match.ranking_weight": "0.02",
"readability_match.max_grade_gap": "3",
"readability_match.penalty_per_grade": "0.10",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.02` — conservative quality guardrail. Readability is a soft preference, not a hard filter. Raise to `0.04` after confirming grades correlate with editorial link quality.
- `max_grade_gap = 3` — allows moderate variation (e.g., grade 7 to grade 10) without penalty. This accommodates normal editorial range within a site section.
- `penalty_per_grade = 0.10` — each grade beyond the gap costs 10% of the signal. A 5-grade excess produces a 50% penalty. Aggressive enough to matter, gentle enough not to dominate.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- multi-language readability formulas (Coleman-Liau, Dale-Chall, SMOG)
- ML-based readability models (neural readability predictors)
- per-section readability scoring (intro vs body vs conclusion)
- reading level as a user-facing display in the review UI (grade shown in diagnostics only)
- any dependency on analytics or telemetry data
- any modification to stored text or embeddings
