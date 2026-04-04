# FR-043 - Semantic Drift Penalty

## Confirmation

- `FR-043` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no semantic-drift or document-coherence penalty exists in the current ranker;
  - nearby signals such as `score_semantic`, `FR-038`, and `FR-039` measure topic match or novelty, but none ask whether a destination starts on-topic and then wanders away;
  - `ContentItem.distilled_text` and `Post.clean_text` already provide plain text suitable for deterministic block-level analysis.

## Current Repo Map

### Existing nearby signals

- `score_semantic`
  - measures overall semantic similarity between host and destination;
  - it does not inspect topic consistency across the destination itself.

- `FR-038` information gain
  - rewards destinations that add genuinely new content;
  - it does not penalize later sections that drift off-topic.

- `FR-039` entity salience match
  - checks whether the destination covers the source page's important terms;
  - it does not inspect whether the destination remains coherent from beginning to end.

### Gap this FR closes

The repo can currently identify pages that appear relevant overall, but it cannot tell when a page is only relevant in the opening section and then turns into unrelated filler, forum detours, template leftovers, or mixed-topic noise.

## Source Summary

### Paper lineage: TextTiling (Hearst, ACL 1994)

Plain-English read:

- long documents can be segmented by looking at lexical similarity between adjacent text blocks;
- sharp drops in similarity often indicate topic boundaries;
- segmentation depth scores can be used to identify where a document changes subject.

Repo-safe takeaway:

- semantic drift can be approximated without heavyweight NLP;
- a block-similarity curve is enough to detect when a page stops talking about its main topic;
- the first coherent segment is a practical "anchor topic" for the rest of the page.

### Patent: US8185378B2 - Text coherence determination

Plain-English read:

- the patent models coherence by comparing textual units and their relationships;
- lower coherence indicates that nearby portions of the document are less semantically connected;
- coherence can be used as a quality signal distinct from topical relevance.

Repo-safe takeaway:

- semantic drift belongs as a separate quality-like penalty;
- it should be computed from within-document consistency, not folded into the main similarity score.

## Plain-English Summary

Simple version first.

Some pages look relevant at the top, but halfway through they drift into unrelated material.

FR-043 penalizes those pages.

Examples:

- a guide that starts about "OLED monitor calibration" and later turns into generic monitor shopping advice;
- a long forum compilation where the early posts match the topic but later quotes and tangents do not;
- a page assembled from multiple snippets that never stays focused on one subject.

The goal is not to punish every subtopic change. The goal is to catch obvious topic drift.

## Problem Statement

Today the ranker can reward relevant destinations even when much of the page is not actually about the promised topic. This can produce suggestions that look good in previews but disappoint the reader after the opening paragraphs.

FR-043 adds a bounded drift penalty so focused destinations are preferred over pages that lose topical coherence.

## Goals

FR-043 should:

- add a separate, explainable semantic-drift penalty;
- analyze topic consistency across the destination text itself;
- stay neutral for short pages where drift cannot be measured reliably;
- penalize only meaningful later-topic divergence, not normal sectioning;
- fit the repo without heavy transformer inference in v1.

## Non-Goals

FR-043 does not:

- replace `score_semantic`, `FR-038`, or `FR-039`;
- require sentence embeddings for every sentence in v1;
- judge writing style, grammar, or factual truth;
- moderate content or hide pages automatically;
- penalize pages merely for covering two closely related subtopics.

## Math-Fidelity Note

### Input text

Prefer:

- `Post.clean_text` when available;
- otherwise `ContentItem.distilled_text`.

### Step 1 - tokenize into ordered terms

Use the repo's existing normalized tokenizer.

- lowercase;
- strip punctuation;
- drop empty tokens.

### Step 2 - split into token blocks

Build ordered token blocks:

- `tokens_per_sequence = 20`
- `block_size_in_sequences = 6`

This yields overlapping comparison windows that are large enough to smooth out sentence noise.

### Step 3 - compute adjacent block similarity

For each boundary `i`, compare the term-frequency vectors of:

- left block `L_i`
- right block `R_i`

Use cosine similarity:

```text
adjacent_similarity(i) = dot(L_i, R_i) / (||L_i|| * ||R_i||)
```

### Step 4 - compute depth scores

Using the TextTiling pattern, estimate how deep each local valley is:

```text
depth(i) = (left_peak(i) - adjacent_similarity(i)) + (right_peak(i) - adjacent_similarity(i))
```

Where:

- `left_peak(i)` is the highest adjacent similarity to the left before the curve starts falling again;
- `right_peak(i)` is the highest adjacent similarity to the right before the curve starts falling again.

### Step 5 - derive topic segments

Mark a topic boundary when:

```text
depth(i) >= mean_depth + 1.0 * std_depth
```

Then segment the document across those boundaries.

Fallback:

- if there are fewer than 3 candidate boundaries, treat the document as one segment.

### Step 6 - define the anchor topic

Use the first segment as the anchor segment, because the opening section is what the host preview and human reviewer will usually judge first.

Build a normalized term-frequency vector for the anchor segment:

```text
A = normalized_tf(anchor_segment)
```

### Step 7 - measure later-segment drift

For every later segment `S_j`, compute anchor similarity:

```text
anchor_similarity(j) = dot(A, S_j) / (||A|| * ||S_j||)
```

Mark a segment as drifted when:

```text
anchor_similarity(j) < anchor_similarity_threshold
```

Default:

- `anchor_similarity_threshold = 0.18`

### Step 8 - aggregate drift ratio

Let:

- `later_segment_count = max(total_segments - 1, 0)`
- `drifted_segment_count = count(anchor_similarity(j) < threshold)`

Then:

```text
drift_ratio = drifted_segment_count / later_segment_count
```

Fallback:

- if `later_segment_count = 0`, drift is undefined and the score is neutral.

### Final bounded score

Store a penalty-oriented bounded score:

```text
semantic_drift_penalty_score =
    0.5,                                if later_segment_count = 0
    0.5 + 0.5 * drift_ratio,            otherwise
```

Interpretation:

- `0.5` = neutral, no measurable drift
- `1.0` = severe drift across most later segments

## Proposed Data Model

### New field on `ContentItem`

Add:

```python
semantic_drift_penalty_score = models.FloatField(
    null=True,
    blank=True,
    default=None,
    help_text="Bounded semantic drift penalty score in [0.5, 1.0].",
)
```

### New fields on `Suggestion`

Add:

```python
score_semantic_drift_penalty = models.FloatField(
    null=True,
    blank=True,
    default=None,
    help_text="Bounded semantic drift penalty copied from destination analysis.",
)

semantic_drift_diagnostics = models.JSONField(
    null=True,
    blank=True,
    default=None,
    help_text="Drift diagnostics for reviewer and operator inspection.",
)
```

### Suggested diagnostics shape

```json
{
  "segment_count": 4,
  "later_segment_count": 3,
  "drifted_segment_count": 2,
  "drift_ratio": 0.667,
  "anchor_similarity_threshold": 0.18,
  "anchor_similarities": [0.31, 0.14, 0.11]
}
```

## Ranking Hook

This is a penalty signal, not a boost signal.

### Default-safe rule

- compute diagnostics and persist the score;
- keep `semantic_drift.ranking_weight = 0.0` by default;
- do not alter suggestion ordering until the operator enables the weight.

### When enabled

Convert the bounded penalty to a `0..1` component:

```text
semantic_drift_component =
    max(0.0, min(1.0, 2.0 * (score_semantic_drift_penalty - 0.5)))
```

Apply subtractively:

```text
score_final =
    score_final - (semantic_drift.ranking_weight * semantic_drift_component)
```

Default:

- `semantic_drift.ranking_weight = 0.0`

## Settings Contract

Add new settings:

```json
{
  "semantic_drift": {
    "enabled": true,
    "ranking_weight": 0.0,
    "tokens_per_sequence": 20,
    "block_size_in_sequences": 6,
    "anchor_similarity_threshold": 0.18,
    "min_word_count": 180
  }
}
```

Rules:

- if destination word count is below `min_word_count`, return neutral `0.5`;
- settings are operator-editable in the advanced ranking area, but hidden behind an "experimental quality penalties" subsection.

## Pipeline Placement

### Where to compute

Compute once per destination before suggestion assembly:

- destination-level analysis during pipeline preprocessing or cached content-signal enrichment;
- copy the stored score into `Suggestion.score_semantic_drift_penalty` when the destination is attached.

### Hard boundary

Do not recompute full text segmentation separately for every host-destination pair. This is destination-intrinsic and should be cached.

## Backend Touch Points

- `backend/apps/content/models.py`
  - add `semantic_drift_penalty_score`

- `backend/apps/content/migrations/`
  - add schema migration

- `backend/apps/pipeline/models.py`
  - add suggestion score + diagnostics fields

- `backend/apps/pipeline/services/`
  - add a deterministic semantic-drift scorer module
  - wire the copied score into suggestion assembly

- `backend/apps/api/`
  - expose settings and diagnostics in existing ranking/settings endpoints

- `frontend/src/app/settings/`
  - add enable toggle and weight slider in the experimental-ranking subsection

- `frontend/src/app/review/`
  - optionally surface drift diagnostics in the suggestion detail view later

## Native Runtime Plan

Per `docs/NATIVE_RUNTIME_POLICY.md`:

- Python implementation first as the reference path;
- optional hot-path native port later at `backend/extensions/semanticdrift.cpp`;
- same formulas, thresholds, and neutral fallbacks in both implementations.

Do not create a second diagnostics surface. Reuse existing pipeline diagnostics plumbing.

## Verification Plan

### Unit tests

- focused page with consistent sections stays near neutral
- page with clearly unrelated later sections receives a higher penalty
- short page under `min_word_count` returns neutral `0.5`
- single-segment page returns neutral `0.5`
- boundary detection remains deterministic for repeated runs

### Integration tests

- pipeline stores `semantic_drift_penalty_score` on destinations
- suggestion rows copy the destination score and diagnostics correctly
- `ranking_weight = 0.0` changes nothing in final ordering
- enabling the weight penalizes high-drift destinations and leaves low-drift pages largely unchanged

## Rollout Guidance

Recommended rollout:

1. ship schema + scorer + diagnostics with `ranking_weight = 0.0`
2. inspect reviewer-facing drift diagnostics on real content
3. calibrate thresholds for forum pages versus article pages
4. enable with a small penalty weight only after false-positive review

## Acceptance Criteria

FR-043 is complete when:

- destination pages can store a bounded semantic-drift penalty score;
- suggestions expose that score and diagnostics;
- settings allow the signal to run in shadow mode with zero ranking effect by default;
- enabling the weight subtracts only the drift component and leaves existing ranking signals untouched.
