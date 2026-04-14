# FR-098 - Dominant Passage Centrality

## Confirmation

- **Backlog confirmed**: `FR-098 - Dominant Passage Centrality` is a new pending request being added to `FEATURE-REQUESTS.md` in this session.
- **Repo confirmed**: No passage-centrality or sentence-importance signal exists in the current ranker. All existing passage-related signals operate on different axes:
  - FR-053 measures passage *relevance to the host* using dense embeddings;
  - FR-043 measures topic *drift* across the document using TextTiling block similarity;
  - FR-054 measures *boilerplate ratio* using content-to-chrome proportion.
- **Repo confirmed**: `ContentItem.distilled_text` provides the cleaned body text needed for segmentation and scoring. No new data sources are required.

## Current Repo Map

### Existing nearby signals

- `FR-053` passage-level relevance
  - breaks destination into passages and embeds each one;
  - finds the passage that best matches the host sentence via cosine similarity;
  - answers "which passage is most relevant to the host?" — a host-dependent question.

- `FR-043` semantic drift penalty
  - uses TextTiling block similarity to segment the document;
  - compares later segments to the opening anchor segment;
  - answers "does the page wander off its opening topic?" — a coherence question.

- `FR-054` boilerplate-to-content ratio
  - compares distilled_text length to total visible page text;
  - answers "how much of this page is real content versus chrome?" — a structural question.

### Gap this FR closes

The repo cannot currently tell whether a destination page has a strong, coherent core passage — a section where the sentences agree with each other and form a concentrated, self-reinforcing information cluster. FR-098 fills this gap.

A page might pass all existing filters (low drift, good boilerplate ratio, decent relevance) and still be a weak destination because its content is scattered across unrelated bullet points, shallow FAQ answers, or loosely connected paragraphs. FR-098 catches that.

## Source Summary

### Paper 1: TextTiling (Hearst, 1997)

**Full citation:** Hearst, M. A. (1997). TextTiling: Segmenting text into multi-paragraph subtopic passages. *Computational Linguistics*, 23(1), 33-64.

**Plain-English description:**

Long documents can be split into topically coherent sections by measuring how much vocabulary two adjacent blocks of text share. When the vocabulary overlap drops sharply, that usually means the topic changed. These boundaries divide the document into passages that each talk about one subtopic.

**Repo-safe takeaway:**

- TextTiling is already used in FR-043 for drift detection, so the segmentation code can be shared;
- FR-098 uses TextTiling only for passage boundary detection, not for drift scoring;
- the segmentation step is deterministic and lightweight (term-frequency vectors, no ML model needed).

**What is directly supported by the paper:**

- splitting documents into topically coherent passages using lexical similarity;
- using depth scores at similarity valleys to find boundary points;
- the method works without training data or domain-specific tuning.

**What is adapted for this repo:**

- the passages produced by TextTiling become the input units for LexRank centrality scoring;
- FR-043 uses TextTiling to *score drift*; FR-098 uses it only to *define passage boundaries*.

### Paper 2: LexRank (Erkan & Radev, 2004)

**Full citation:** Erkan, G., & Radev, D. R. (2004). LexRank: Graph-based lexical centrality as salience and cohesion measures in text summarization. *Journal of Artificial Intelligence Research*, 22, 457-479. DOI: 10.1613/jair.1523

**Also presented at:** Erkan, G., & Radev, D. R. (2004). LexRank: Graph-based lexical centrality for multi-document summarization. *EMNLP 2004*.

**Plain-English description:**

LexRank builds a graph where each sentence is a node. Two sentences are connected by an edge if their TF-IDF cosine similarity exceeds a threshold. Then it runs PageRank on this graph. Sentences that are similar to many other important sentences get high centrality scores. The most central sentences are the ones that best represent the overall content.

Think of it like a popularity contest among sentences: a sentence is important if it is similar to other sentences that are themselves important.

**Repo-safe takeaway:**

- LexRank uses only TF-IDF vectors and cosine similarity — no ML model, no GPU, no external API;
- the PageRank-style power iteration converges in a few dozen iterations for typical page lengths;
- the output is a centrality score per sentence that naturally identifies the "core" content;
- a passage whose sentences all have high centrality is a strong, self-reinforcing information cluster.

**What is directly supported by the paper:**

- constructing a sentence similarity graph using TF-IDF cosine similarity;
- applying eigenvector centrality (PageRank) to find the most representative sentences;
- using a cosine similarity threshold to sparsify the graph;
- the method is unsupervised and language-agnostic.

**What is adapted for this repo:**

- instead of extracting summary sentences, FR-098 aggregates sentence centrality scores per passage to find the dominant passage;
- the dominant passage score becomes a ranking signal, not a text extraction tool;
- the threshold and damping parameters are set to published defaults from the paper.

### Patent: US7752534B2 — Centrality-Based Document Scoring

**Plain-English description:**

This patent describes using graph-based centrality measures on text units within a document to assess content quality. Documents with higher internal centrality — where units reinforce each other — are scored as higher quality.

**Repo-safe takeaway:**

- passage-level centrality is a legitimate quality signal distinct from relevance matching;
- internal document centrality is complementary to external relevance (host-to-destination) scoring.

## Plain-English Summary

Simple version first.

Imagine you have a page with 5 paragraphs. In one of those paragraphs, every sentence reinforces the others — they all talk about the same thing from different angles. That paragraph is the "dominant passage." It's the concentrated core of the page.

Now imagine another page where every paragraph is about something slightly different, and no sentences really agree with each other. That page has no dominant passage — it's scattered.

FR-098 finds the dominant passage and measures how strong it is. Pages with a strong core get a higher score. Pages that are scattered get a neutral score.

This is different from:

- **FR-053** (passage relevance) — which asks "does any passage match the host?" FR-098 doesn't care about the host at all. It asks "does this page have a strong core?"
- **FR-043** (semantic drift) — which asks "does the page wander off-topic?" FR-098 doesn't care about wandering. It asks "is there a passage where sentences really agree with each other?"
- **FR-054** (boilerplate ratio) — which asks "how much of the page is content vs chrome?" FR-098 only looks at the content and asks "is the content concentrated or scattered?"

## Problem Statement

Today the ranker can identify pages that are relevant, coherent, and content-rich. But it cannot distinguish between a page where the content forms a strong, concentrated argument and a page where the content is a loose collection of related-but-shallow points.

Two pages can have identical semantic similarity, zero drift, and high content ratio — but one has a paragraph that is a dense, self-reinforcing cluster of information, while the other spreads thin across many loosely related bullet points.

FR-098 closes this gap by identifying the most central passage in the destination and scoring its strength.

## Goals

FR-098 should:

- add a separate, explainable, bounded passage-centrality signal;
- segment destination body text into passages using TextTiling boundaries;
- score sentences within each passage using LexRank centrality;
- identify the dominant passage (highest mean sentence centrality);
- stay neutral for pages too short to segment meaningfully;
- keep ranking impact additive, bounded, and off by default;
- use only `ContentItem.distilled_text` as input — not title, not total page text, not raw HTML;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-098 does not:

- replace FR-053 — passage centrality and passage relevance are complementary;
- replace FR-043 — centrality and drift measure different things;
- use any ML model, GPU computation, or external API;
- use the page title, raw HTML, or any page-chrome text for scoring;
- use analytics, reviewer feedback, or live query data;
- extract or display the dominant passage text to the user (that is a future feature);
- implement production code in the spec pass.

## Math-Fidelity Note

### Input text

Use `ContentItem.distilled_text` (cleaned body text only).

Explicitly excluded:

- `ContentItem.title` — can be misleading, spammy, or unrelated to body content;
- total page text — FR-054 territory;
- raw HTML — irrelevant to passage quality measurement.

### Step 1 — Sentence tokenization

Split `distilled_text` into sentences using a sentence boundary detector.

```text
sentences = sentence_tokenize(distilled_text)
```

Filter out junk sentences:

```text
usable_sentences = [s for s in sentences if word_count(s) >= 5]
```

**Safety rule:** if `len(usable_sentences) < 3`, return neutral `0.5` immediately. There are too few sentences to build a meaningful centrality graph.

### Step 2 — TextTiling segmentation

Reuse the TextTiling segmentation approach from FR-043 to find passage boundaries.

Let:

- `tokens_per_sequence = 20`
- `block_size_in_sequences = 6`

Build token blocks, compute adjacent block cosine similarity, compute depth scores:

```text
adjacent_similarity(i) = dot(L_i, R_i) / (||L_i|| * ||R_i||)

depth(i) = (left_peak(i) - adjacent_similarity(i))
         + (right_peak(i) - adjacent_similarity(i))
```

Mark topic boundaries where:

```text
depth(i) >= mean_depth + 1.0 * std_depth
```

Split the document at these boundaries to produce passage segments.

**Fallback:** if TextTiling produces fewer than 2 segments, treat the entire document as one passage.

### Step 3 — TF-IDF sentence vectors

Build a TF-IDF matrix across all usable sentences in the document.

For each sentence `s_i`, compute the TF-IDF vector:

```text
tfidf(s_i) = [tf(t, s_i) * idf(t, D) for each term t]
```

Where:

- `tf(t, s_i) = count(t in s_i) / len(s_i)` — term frequency within the sentence;
- `idf(t, D) = log(N / (1 + df(t, D)))` — inverse document frequency across all sentences in this page;
- `N = len(usable_sentences)`;
- `df(t, D) = count(sentences containing t)`.

Source: Erkan & Radev (2004), Section 3.1.

### Step 4 — Sentence similarity graph

Build a similarity matrix over all usable sentences:

```text
sim(i, j) = cosine(tfidf(s_i), tfidf(s_j))
```

Apply a threshold to create the adjacency matrix:

```text
A(i, j) = 1 if sim(i, j) >= threshold else 0
```

Default threshold: `0.10`

Source: Erkan & Radev (2004), Section 3.2. The paper uses a threshold of 0.1 for the continuous LexRank variant.

Build the weighted transition matrix (row-stochastic):

```text
M(i, j) = sim(i, j) / sum(sim(i, k) for all k where A(i, k) = 1)
```

If sentence `i` has no edges (isolated node), set `M(i, j) = 1/N` for all `j` (uniform distribution).

### Step 5 — LexRank centrality (power iteration)

Compute eigenvector centrality using the damped PageRank formula:

```text
p(i) = d/N + (1 - d) * sum(M(j, i) * p(j) for all j)
```

Where:

- `d = 0.15` — damping factor (probability of random jump);
- `N = len(usable_sentences)`;
- `p` is initialized to `1/N` for all sentences.

Source: Erkan & Radev (2004), Equation 3. The paper uses `d = 0.15` following the original PageRank convention.

Iterate until convergence:

```text
max_iterations = 100
convergence_threshold = 1e-6

repeat:
    p_new(i) = d/N + (1 - d) * sum(M(j, i) * p(j) for all j)
    if max(|p_new(i) - p(i)| for all i) < convergence_threshold:
        break
    p = p_new
```

The result is a centrality score `p(i)` for each sentence.

### Step 6 — Passage centrality aggregation

For each passage `P_k` (from TextTiling boundaries), compute the mean sentence centrality:

```text
passage_centrality(k) = mean(p(i) for all i where sentence i is in passage P_k)
```

The dominant passage is the one with the highest mean centrality:

```text
dominant_index = argmax(passage_centrality(k) for all k)
dominant_centrality = passage_centrality(dominant_index)
```

### Step 7 — Normalization to bounded score

Normalize the dominant passage centrality to a `[0, 1]` range.

The baseline centrality for uniformly distributed sentences is `1/N`. The dominant passage centrality will typically be higher than this. Normalize relative to the baseline:

```text
centrality_ratio = dominant_centrality / (1/N)
                 = dominant_centrality * N
```

For a page with uniform sentence importance, `centrality_ratio = 1.0`. For a page with a strong dominant passage, `centrality_ratio > 1.0`. Cap at a reasonable maximum:

```text
max_ratio = 3.0

normalized = min(1.0, (centrality_ratio - 1.0) / (max_ratio - 1.0))
```

This maps:

- `centrality_ratio = 1.0` (uniform — no dominant passage) -> `normalized = 0.0`
- `centrality_ratio = 3.0` (very strong dominant passage) -> `normalized = 1.0`

### Step 8 — Final bounded score

```text
score_passage_centrality = 0.5 + 0.5 * normalized
```

This maps:

- uniform centrality (no dominant passage) -> `score = 0.5` (neutral)
- strong dominant passage -> `score` approaches `1.0`

**Neutral fallback:**

```text
score_passage_centrality = 0.5
```

Used when:

- `distilled_text` has fewer than 200 characters;
- fewer than 3 usable sentences after junk filtering;
- TextTiling or LexRank computation fails for any reason;
- feature is disabled.

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_passage_centrality_component =
    max(0.0, min(1.0, 2.0 * (score_passage_centrality - 0.5)))
```

```text
score_final += passage_centrality.ranking_weight * score_passage_centrality_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-098 must stay separate from:

- `FR-053` passage-level relevance
  - FR-053 measures host-sentence-to-best-destination-passage similarity (a host-dependent score);
  - FR-098 measures the centrality of the destination's strongest passage (a host-independent score);
  - different axis entirely: relevance vs internal importance.

- `FR-043` semantic drift penalty
  - FR-043 measures whether later segments diverge from the opening anchor topic;
  - FR-098 measures whether any passage concentrates sentence agreement;
  - a page can have zero drift but still have no dominant passage (evenly distributed content);
  - a page can have high drift but still have a strong dominant passage in one section.

- `FR-054` boilerplate-to-content ratio
  - FR-054 measures content volume relative to page chrome;
  - FR-098 measures content *quality* within the body text only;
  - a page can have excellent boilerplate ratio (90% content) but still be scattered.

- `score_semantic`
  - semantic measures host-to-destination similarity at document level;
  - FR-098 measures destination internal structure quality;
  - completely independent axes.

Hard rule: FR-098 must not modify any text field, embedding, or score used by any other signal.

## Inputs Required

FR-098 v1 needs:

- `ContentItem.distilled_text` — for sentence tokenization and TextTiling segmentation

Explicitly disallowed FR-098 inputs in v1:

- `ContentItem.title`
- total page text or raw HTML
- page-level or passage-level embeddings (FR-053 territory)
- analytics or telemetry data
- host sentence or host page data (this is a destination-intrinsic signal)

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `passage_centrality.enabled`
- `passage_centrality.ranking_weight`
- `passage_centrality.similarity_threshold`
- `passage_centrality.damping_factor`
- `passage_centrality.max_iterations`
- `passage_centrality.min_sentences`
- `passage_centrality.min_body_chars`
- `passage_centrality.max_ratio`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `similarity_threshold = 0.10`
- `damping_factor = 0.15`
- `max_iterations = 100`
- `min_sentences = 3`
- `min_body_chars = 200`
- `max_ratio = 3.0`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.05 <= similarity_threshold <= 0.30`
- `0.05 <= damping_factor <= 0.30`
- `50 <= max_iterations <= 500`
- `2 <= min_sentences <= 10`
- `100 <= min_body_chars <= 500`
- `2.0 <= max_ratio <= 5.0`

### Feature-flag behavior

- `enabled = false`
  - skip centrality scoring entirely
  - store `score_passage_centrality = 0.5`
  - store `passage_centrality_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute centrality scores and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.passage_centrality_diagnostics`

Required fields:

- `score_passage_centrality`
- `passage_centrality_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_body_too_short`
  - `neutral_too_few_sentences`
  - `neutral_processing_error`
- `total_sentences` — count of usable sentences after junk filtering
- `passage_count` — number of TextTiling passages
- `dominant_passage_index` — which passage (0-indexed) scored highest
- `dominant_passage_centrality` — raw mean centrality of the dominant passage
- `centrality_ratio` — how many times above baseline the dominant passage scores
- `all_passage_centralities` — list of mean centrality per passage (for operator inspection)
- `convergence_iterations` — how many power-iteration steps LexRank needed
- `similarity_threshold_used` — setting value used for this run
- `damping_factor_used` — setting value used for this run

### Suggested diagnostics shape

```json
{
  "score_passage_centrality": 0.72,
  "passage_centrality_state": "computed",
  "total_sentences": 28,
  "passage_count": 4,
  "dominant_passage_index": 1,
  "dominant_passage_centrality": 0.058,
  "centrality_ratio": 1.62,
  "all_passage_centralities": [0.031, 0.058, 0.042, 0.029],
  "convergence_iterations": 23,
  "similarity_threshold_used": 0.10,
  "damping_factor_used": 0.15
}
```

Plain-English review helper text should say:

- `Passage centrality measures whether the destination has a strong, concentrated core section.`
- `A high score means the page has a passage where sentences strongly reinforce each other.`
- `A neutral score means the content is evenly distributed across the page with no standout section, or the page was too short to analyze.`

## Storage / Model / API Impact

### Content model

Add:

- `ContentItem.passage_centrality_score: FloatField(default=None, null=True, blank=True)` — bounded score in `[0.5, 1.0]`

### Suggestion model

Add:

- `Suggestion.score_passage_centrality: FloatField(default=0.5)` — copied from destination at suggestion time
- `Suggestion.passage_centrality_diagnostics: JSONField(default=dict, blank=True)` — full diagnostics

### Estimated storage

Per destination page:

- 1 FloatField = 8 bytes
- 1 JSONField (diagnostics) = ~200 bytes average

For 100K pages:

- Content model: 100K x 8 bytes = ~0.8 MB
- Suggestion model: depends on suggestion count, but diagnostics JSON ~200 bytes per suggestion
- **Total steady-state estimate: ~5-10 MB** including suggestions

30-day growth: negligible (score is recalculated on re-crawl, not accumulated).
90-day growth: same — no historical accumulation.

### PipelineRun snapshot

Add FR-098 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/passage-centrality/`
- `PUT /api/settings/passage-centrality/`

### Review / admin / frontend

Add one new review row:

- `Passage Centrality`

Add one small diagnostics block:

- dominant passage index and centrality score
- centrality ratio (how far above baseline)
- passage count and sentence count
- all passage centralities (for operator deep-dive)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- advanced section: similarity threshold, damping factor, max iterations, min sentences, min body chars, max ratio

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/passage_centrality.py` — new service file (TextTiling segmentation, LexRank scoring, dominant passage detection)
- `backend/apps/pipeline/services/ranker.py` — add FR-098 additive hook
- `backend/apps/pipeline/services/pipeline.py` — integrate centrality scoring at content enrichment time
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/content/models.py` — add centrality score field
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-098 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoints
- `backend/apps/api/urls.py` — wire new settings endpoints
- `backend/apps/pipeline/tests.py` — FR-098 unit tests
- `backend/benchmarks/test_bench_passage_centrality.py` — mandatory benchmark (3 input sizes)
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-098 implementation pass:

- FR-053 passage embedding infrastructure (separate FAISS index)
- FR-043 semantic drift scorer (separate signal, separate diagnostics)
- existing page-level embeddings or FAISS indices
- `backend/apps/graph/models.py` — no new graph edges

## Pipeline Placement

### Where to compute

Compute once per destination during content enrichment (same phase as FR-043 and FR-054):

- destination-level analysis during pipeline preprocessing;
- store `passage_centrality_score` on `ContentItem`;
- copy the stored score into `Suggestion.score_passage_centrality` when the destination is attached.

### Hard boundary

Do not recompute LexRank separately for every host-destination pair. This is destination-intrinsic and must be cached on `ContentItem`.

### Performance budget

- TextTiling segmentation: ~2-5 ms per page (term-frequency vectors, no ML)
- TF-IDF matrix construction: ~1-3 ms per page (sparse matrix for ~30 sentences)
- LexRank power iteration: ~1-5 ms per page (N x N matrix for N ~ 30, converges in ~20 iterations)
- **Total: < 15 ms per page** on i5-12450H — well within the 50 ms Python budget
- Batch processing: can process pages independently in parallel via Celery

## Native Runtime Plan

Per `docs/NATIVE_RUNTIME_POLICY.md`:

- Python implementation first as the reference path;
- optional hot-path native port later at `backend/extensions/passagecentrality.cpp`;
- same formulas, thresholds, and neutral fallbacks in both implementations.

A C++ port is unlikely to be needed — this is computed once per destination at index time, not per host-destination pair at suggestion time. The 15 ms Python budget is comfortable.

## Test Plan

### 1. Sentence tokenization and filtering

- 500-word text produces ~25 usable sentences
- sentences shorter than 5 words are filtered out
- text with fewer than 3 usable sentences returns neutral `0.5`

### 2. TextTiling segmentation

- long coherent document segments into 3-5 passages
- single-topic short document treated as one passage
- passage boundaries respect topic shifts

### 3. LexRank centrality

- page where all sentences are about the same subtopic: dominant passage centrality is near baseline (uniform)
- page with one tightly focused paragraph and several loose paragraphs: dominant passage centrality is well above baseline
- isolated sentences (no edges in graph) get uniform centrality `1/N`

### 4. Dominant passage selection

- dominant passage is the passage with the highest mean sentence centrality
- ties broken by first occurrence (lower index)

### 5. Neutral fallback cases

- `distilled_text` < 200 chars -> `score = 0.5`, state `neutral_body_too_short`
- fewer than 3 usable sentences -> `score = 0.5`, state `neutral_too_few_sentences`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`
- processing error -> `score = 0.5`, state `neutral_processing_error`

### 6. Bounded score

- score is always in `[0.5, 1.0]` regardless of input
- `centrality_ratio` is capped at `max_ratio`

### 7. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 8. Isolation from other signals

- FR-098 does not modify any field used by FR-053, FR-043, or FR-054
- changing `score_semantic` does not affect `score_passage_centrality`
- no page-level embedding or FAISS index is modified

### 9. Determinism

- same input text produces same score on repeated runs
- no random initialization (LexRank starts from uniform `1/N`)

### 10. Serializer and frontend contract

- `score_passage_centrality` and `passage_centrality_diagnostics` appear in suggestion detail API response
- review dialog renders the `Passage Centrality` row
- settings page loads and saves FR-098 settings

### 11. Benchmark coverage

- `backend/benchmarks/test_bench_passage_centrality.py` with 3 input sizes:
  - small: 10 sentences, 1 passage
  - medium: 30 sentences, 3-4 passages
  - large: 100 sentences, 8-10 passages
- all must complete under 50 ms per page on i5-12450H

### 12. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-098 settings and algorithm version

## Rollout Plan

### Step 1 — Schema and scorer

- add model fields and migrations
- implement `passage_centrality.py` service
- compute centrality scores for all destinations
- verify scores distribute sensibly across the site

### Step 2 — Diagnostics only

- deploy with `ranking_weight = 0.0`
- verify diagnostics appear in the review dialog
- inspect dominant passage indices — do they correspond to the strongest sections?

### Step 3 — Operator review

- compare `score_passage_centrality` across known strong vs weak pages
- verify pages with a clear "core topic" section score higher than scattered pages
- check that short pages reliably return neutral

### Step 4 — Optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.05`

## Risk List

- TextTiling segmentation quality varies with writing style — mitigated by treating single-segment pages as neutral (not penalized, not boosted);
- LexRank assumes TF-IDF captures sentence similarity — may underperform on highly technical content with specialized vocabulary — mitigated by the similarity threshold (0.10) being low enough to capture topical overlap even with varied terminology;
- power iteration adds computation cost — mitigated by the convergence threshold and max iteration cap, and by the fact that N (sentence count per page) is typically < 50;
- `max_ratio = 3.0` is a heuristic cap — may need tuning after real data inspection — mitigated by making it a setting;
- storage impact (~5-10 MB) is negligible given the 59 GB free disk space.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"passage_centrality.enabled": "true",
"passage_centrality.ranking_weight": "0.0",
"passage_centrality.similarity_threshold": "0.10",
"passage_centrality.damping_factor": "0.15",
"passage_centrality.max_iterations": "100",
"passage_centrality.min_sentences": "3",
"passage_centrality.min_body_chars": "200",
"passage_centrality.max_ratio": "3.0",
```

**Why these values:**

- `enabled = true` — compute and store diagnostics from day one;
- `ranking_weight = 0.0` — diagnostics-only mode until operator validates the signal on real data;
- `similarity_threshold = 0.10` — published default from Erkan & Radev (2004), Section 3.2;
- `damping_factor = 0.15` — published default from PageRank convention used in the paper;
- `max_iterations = 100` — generous cap; convergence is typically reached in 20-30 iterations;
- `min_sentences = 3` — minimum needed for a meaningful centrality graph;
- `min_body_chars = 200` — consistent with FR-054's minimum threshold;
- `max_ratio = 3.0` — conservative normalization cap; pages exceeding 3x baseline centrality are all treated as "very strong."

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- extracting and displaying the dominant passage text to the user (future enhancement)
- using dense embeddings instead of TF-IDF for sentence similarity (FR-053 territory)
- cross-document centrality (comparing passages across different destination pages)
- using title or page-chrome text as scoring input
- any dependency on analytics, telemetry, or host-page data
- any modification to page-level embeddings, passage embeddings, or FAISS indices
- C++ native port in v1 (performance budget is comfortable in Python)
