# FR-053 - Passage-Level Relevance Scoring

## Summary

Score destination pages at sub-document granularity. The current
ranker compares a host sentence to a destination's full-page
embedding; FR-053 chunks the destination's body into ~200-token
passages, embeds each one, and uses the best-matching passage's
similarity as the score. Long pages with one perfectly-relevant
section deep in the body finally rank where they should — instead
of having that one great section averaged away by nine mediocre
ones.

## Confirmation

- **Backlog confirmed**: `FR-053 - Passage-Level Relevance Scoring` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No passage-level or sub-document relevance signal exists in the current ranker. All existing relevance signals (`score_semantic`, `score_keyword`, `score_field_aware_relevance`) operate at full-document granularity. FR-053 scores the *best-matching passage* within the destination page — a fundamentally finer granularity.
- **Repo confirmed**: FAISS vector search and BGE-M3 embeddings are already established in the pipeline. FR-053 extends this infrastructure to passage-level embeddings without replacing it.
- **Group D.1 alignment (2026-04-28 amendment)**: After Group D.1 of the masterplan shipped, the page-level embedding source is now `Post.clean_text` (full body) instead of `distilled_text` (5-sentence summary). FR-053's chunk source must therefore also be `Post.clean_text` so passage segmentation reads from the same canonical text. Chunking the 5-sentence summary would actively undo D.1's long-content recovery.

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
  - Destination `Post.clean_text` is the chunk source (the full BBCode-stripped body the importer already builds). Group D.1 alignment applies here too.

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

## Academic Source

### Patent: US9940367B1 — Scoring Candidate Answer Passages (Google, 2018)

- Patent number: **US 9,940,367 B1**
- Filing: 2014-12-09; Granted: 2018-04-10; Assignee: Google LLC.
- Inventors: Hugo Zaragoza, Sourabh Tiwari, Eric Tzeng, et al.
- Open access: <https://patents.google.com/patent/US9940367B1>
- Specifically implemented section: column 5 lines 25–48 (passage segmentation as fixed-size word windows) and column 8 lines 5–32 (use the maximum passage score as the document's relevance score).

### Cross-reference for chunking parameters: Callan 1994

- Citation: Callan, J. P. (1994). *Passage-level evidence in document retrieval.* SIGIR 1994: 302–310. DOI: `10.1145/188490.188589`. Open access: <https://dl.acm.org/doi/10.1145/188490.188589>
- Specifically referenced: §5 (window size) — Callan reports 150–300 token windows as the empirical sweet spot across TREC collections, used here to justify `passage_words = 200` (squarely inside Callan's recommended band) and `passages_per_page = 5` (covers a typical 1000-word how-to without over-counting).
- Already cited in [`backend/apps/sources/passages.py:48-51`](../../backend/apps/sources/passages.py:48); FR-053 reuses the same module for chunking.

## Mapping: Paper Variables → Code Variables

| Patent / Paper symbol | Meaning | Code variable / setting |
|---|---|---|
| `D` (document) | Destination page body | `Post.clean_text` (NOT `distilled_text` — see "Group D.1 alignment" above) |
| `p_i` (passage *i* of *D*) | Token-bounded slice of `D` | `Passage.text` returned by `apps.sources.passages.segment_from_sentences` |
| `K` (passages per document) | Cap on passages stored per page | `passage_relevance.passages_per_page` (default 5) |
| `W` (window size in tokens) | Words per passage | `passage_relevance.passage_words` (default 200) |
| `q` (query) | Host sentence embedding | Existing `Sentence.embedding` (1024-dim BGE-M3, L2-normalised) |
| `e(p_i)` (passage embedding) | Dense vector for passage *i* | `PassageEmbedding.embedding` (pgvector(1024), L2-normalised) |
| `score(D, q)` (best-passage score) | max cosine over passages | `score_passage_relevance` (mapped to [0.5, 1.0]) |

## Researched Starting Point

| Setting | Default | Baseline + citation |
|---|---|---|
| `passage_relevance.enabled` | `true` | Masterplan rule "all picks ON by default in Recommended preset". No paper citation needed for a feature flag. |
| `passage_relevance.ranking_weight` | `0.05` | Matches the active-tier weight band of FR-099–FR-105 graph signals (0.04–0.05), all of which are additive contributions to the same composite score per `backend/apps/suggestions/recommended_weights.py:165-176`. The patent recommends max-passage as the document score but does not prescribe a weight in a multi-signal additive composite; this default is the same tier as the project's other shipped passage/graph signals. **`# HEURISTIC: cross-tier match, no primary-source weight`** flag added to the seed comment in `recommended_weights_forward_settings.py` per RANKING-GATES.md §B2 exception (a). Re-validated by TPE auto-tuner after 30-day burn-in per BLC §6.4 / §7.3. |
| `passage_relevance.passages_per_page` | `5` | Callan 1994 SIGIR §5 reports 150–300 token windows are the sweet spot; 5 windows × 200 tokens covers a typical 1000-word how-to without over-counting boilerplate. |
| `passage_relevance.passage_words` | `200` | Callan 1994 SIGIR §5 — squarely inside the empirical 150–300 token band. |
| `passage_relevance.index_quantised` | `true` | Operator-tunable storage flag. V1 ships with float32 pgvector (quantization deferred to a follow-up slice — see `## Pending`). |

## Why This Does Not Overlap With Any Existing Signal

Every currently-live ranker contribution + every relevant pending FR is enumerated below with a one-line non-overlap argument.

### Live signals (15 core + 7 graph topology = 22 as of FR-105)

| Signal | Output type | Why FR-053 is distinct |
|---|---|---|
| `score_semantic` (FR-005) | Cosine similarity to FULL-PAGE BGE-M3 embedding | FR-053 = cosine to BEST-PASSAGE embedding. Different vectors (one per page vs K per page), different aggregation (single cos vs max cos), different output range. |
| `score_keyword` | Sparse token overlap | FR-053 = dense embedding similarity. Different representation entirely. |
| `score_node` (FR-006) | PageRank-derived authority score | FR-053 = passage-level relevance. Different mechanism (graph topology vs text content). |
| `score_field_aware_relevance` (FR-011) | BM25 across title/body/scope/anchor fields | Different scoring function (BM25 vs cosine), different decomposition (fields vs passages). |
| `score_click_distance` (FR-012) | Sitemap depth penalty | FR-053 = text content. Different inputs entirely. |
| `score_link_freshness` (FR-007) | Time-decay on edge timestamp | Different inputs. |
| `score_anchor_diversity` | Anchor-text repetition penalty | Anchor-side vs destination-content-side. |
| `score_phrase_match` (FR-008) | Anchor-expansion phrase match | FR-053 = passage cosine. Different mechanism. |
| `score_learned_anchor` (FR-009) | Anchor vocabulary relevance | Anchor-side. |
| `score_rare_term_propagation` (FR-010) | Rare-term IDF boost | Different mechanism. |
| `score_engagement_quality` | GA4 dwell + scroll | Behavioral, not content. |
| `score_content_value` | Composite quality from analytics | Behavioral. |
| `score_keyword_stuffing` (live anti-signal) | Keyword density penalty | FR-053 doesn't penalise; it boosts. |
| `score_link_farm` (anti-signal) | Reciprocal-link ring detection | Graph-topology, not content. |
| FR-099–FR-105 (DARB / KMIG / TAPB / KCIB / BERP / HGTE / RSQVA) | Graph topology + GSC vocabulary | All graph-derived. FR-053 is content-derived. |
| `score_reference_context` (FR-051, pending) | Host-side window | Source side; FR-053 is destination side. Opposite ends of the link. |

### Pending / forward-declared specs that mention "passage" or text-similarity

- `pick-25-passages` and `apps.sources.passages` — INFRASTRUCTURE only. These produce the segmentation; FR-053 CONSUMES the segmentation. Not duplicate; cooperating modules.
- FR-040 (multimedia richness, pending) — image/video presence. Different inputs.
- FR-052 (readability matching, pending) — Flesch-Kincaid alignment. Different mechanism.
- FR-054 (boilerplate ratio, pending) — content/HTML char ratio. Different scope.

### Meta-algorithms

- FR-014 (near-dup clustering) — clusters at item level by full-page cosine. FR-053 = passage-level. Different granularity, different output (cluster ID vs scalar similarity).
- FR-015 (slate diversity) — post-ranking de-dup. FR-053 contributes a per-pair score; slate diversity reranks. Different stage of the pipeline.
- FR-018 (auto-tuner) — adjusts weights. FR-053 IS one of the weights it can later tune. No interference at runtime.

### Reserved keys

`recommended_weights_forward_settings.py:191-195` already declares `passage_relevance.*` keys — this spec is the implementation for those declarations. No collision.

## Neutral Fallback

`score_passage_relevance` returns `0.5` (neutral, contributes zero to the additive component after the centering at line 220) when:

- The destination has fewer than `passage_words` total words (too short to chunk).
- No passage embeddings are available for the destination (ContentItem has no `PassageEmbedding` rows yet).
- The feature is disabled (`passage_relevance.enabled = false`).
- An exception fires during scoring (`passage_relevance_state = "neutral_processing_error"`).

The neutral behaviour is enforced inside `score_passage_relevance` — the function NEVER raises into `score_destination_matches`. Per RANKING-GATES.md A7, a crash there would kill the whole pipeline.

## Architecture Lane

- **Index-time chunking + embedding generation**: Python in `apps.pipeline.services.passage_relevance` (orchestration) + the existing C++ embedding kernel (BGE-M3 inference). The `apps.sources.passages.segment_from_sentences` chunker is already pure Python and pre-existed.
- **Query-time scoring**: Python via NumPy max-cosine. K=5 passages × 1024 dims is a 5×1024 matrix; max-cosine against a 1024-dim query is microseconds even without C++ acceleration. **Deferred to a follow-up slice**: `backend/extensions/passagesim.cpp` for batch passage similarity at scale (>10k pages).
- **Storage**: pgvector(1024) on a new `PassageEmbedding` model. **Deferred to a follow-up slice**: int8-quantised FAISS index (`faiss.IndexScalarQuantizer`) — V1 ships with the simpler pgvector path.

## Hardware Budget

Numbers below are **estimated for the target machine** (i5-12450H, 16 GB RAM, RTX 3050 6 GB VRAM, 59 GB free disk per BLC §6). Per RANKING-GATES.md A8 these will be **re-validated with measured numbers post-merge**; if any budget is violated the spec gets a `# PERF: pending C++ port` tag in code with a follow-up ticket.

| Resource | Budget | Estimated cost (V1 pgvector path) | Status |
|---|---|---|---|
| Python hot-path / 500 candidates | < 50 ms | ~10 ms (NumPy max-cosine over 5×1024 × 500) | ✓ within budget |
| C++ hot-path / 500 candidates | < 5 ms | n/a in V1 (deferred to passagesim.cpp) | n/a |
| RAM peak (index build, batch=100) | < 10 GB app-headroom | ~200 MB (BGE-M3 already loaded; passages added) | ✓ |
| RAM resident at idle | < 10 GB | passage embeddings live in Postgres, not RAM | ✓ |
| GPU VRAM | < 6 GB (BGE-M3 already ~2.5 GB) | 0 incremental (passage embeds reuse the existing BGE-M3 process) | ✓ |
| Disk @ 100k pages × 5 passages × 1024 dims × 4 bytes (float32) | within 59 GB free | ~2 GB | ✓ |
| Disk @ 30-day projection | — | ~+200 MB / mo (5% page growth) | ✓ |
| Disk @ 90-day projection | — | ~+600 MB / 3 mo | ✓ |

**Caveat per RANKING-GATES.md A8**: these are estimates. Gate A enforcement requires measured numbers via `pytest backend/benchmarks/test_bench_passage_relevance.py` after first deploy. Benchmark file ships in this slice (see `## Benchmark Plan`).

## Real-World Constraints

- **Index rebuild on D.1 backfill**: the long-tail backfill task `pipeline.backfill_long_tail_embeddings` (Group D.8) regenerates page-level embeddings for posts whose body was previously truncated. FR-053's passage embeddings need to ALSO be regenerated for those posts — the chunk source (`clean_text`) is now different. The FR-053 indexer must subscribe to the same checkpoint key OR run after D.8 completes.
- **`distilled_text` drift**: the spec previously said "chunk distilled_text". After Group D.1, that's a 5-sentence summary, not the full body. **The chunk source is now `Post.clean_text`** — explicit in `## Mapping`.
- **No FAISS index modification**: V1 stores passage embeddings in pgvector, not FAISS. The page-level FAISS index is untouched (hard rule). A follow-up slice may add a separate passage-level FAISS index for query-time speedup, but never the same one.
- **Sentence-boundary chunking**: passages are joined whole sentences via `apps.sources.passages.segment_from_sentences`. A passage is never split mid-sentence. Cap of K passages is applied AFTER segmentation by even spacing.

## Diagnostics

`Suggestion.passage_relevance_diagnostics` JSONField with these keys:

- `score_passage_relevance` — final bounded score in [0.5, 1.0]
- `passage_relevance_state` — one of `computed`, `neutral_feature_disabled`, `neutral_destination_too_short`, `neutral_no_passages`, `neutral_processing_error`
- `best_passage_index` — 0-based index of the best-matching passage
- `best_passage_similarity` — raw cosine [0.0, 1.0] of the best passage
- `passage_count` — number of passage embeddings available for the destination
- `all_passage_similarities` — list of cosine values for every passage (for operator inspection)
- `best_passage_preview` — first 100 chars of the best-matching passage
- `passages_per_page_setting` — value used for this run
- `passage_words_setting` — value used for this run

Per BLC §3, the operator can answer four questions from the suggestion-detail UI:
1. *"Why was this destination ranked here?"* → see `score_passage_relevance` in the additive contribution list
2. *"Which paragraph drove the score?"* → see `best_passage_preview`
3. *"Was the signal computed or neutral-fallback?"* → see `passage_relevance_state`
4. *"Are all passages similarly relevant or is one a clear winner?"* → see `all_passage_similarities`

## Benchmark Plan

`backend/benchmarks/test_bench_passage_relevance.py` ships with three input sizes per BLC §1.4:

- **Small (50 candidates × 5 passages)** — single sentence query.
- **Medium (500 candidates × 5 passages)** — typical batch at suggestion time.
- **Large (5000 candidates × 5 passages)** — stress test for batch builds.

Pass criterion: medium batch < 50 ms wall-clock per BLC §6.

## Edge Cases

| Edge case | Handling |
|---|---|
| Destination has < passage_words total words | Single-passage fallback via `apps.sources.passages.segment_from_sentences` (returns one passage = whole text); if even that's too short, return neutral `0.5` |
| Destination has no Post row (rare; cross-source dup-of from Group A.6) | Reuse the canonical's PassageEmbeddings via `duplicate_of` FK |
| BGE-M3 model unavailable (CPU path failed, GPU OOM) | `passage_relevance_state = "neutral_processing_error"`; log to /error-log via ingest_error |
| Passage embedding contains NaN/Inf | Filter the row at query time; if all passages are bad, return neutral `0.5` |
| Passage count > K | `passages_per_page_setting` cap applied at index time via `apps.sources.passages` cap parameter |
| `passage_relevance.enabled = false` | Skip computation; return neutral state `neutral_feature_disabled` |
| `passage_relevance.ranking_weight = 0.0` | Compute + store diagnostics; do not contribute to score_final |

## Gate Justifications

Per RANKING-GATES.md, items where the standard checklist requires explicit justification:

- **A5 (every default cited to a published baseline)**: `passage_relevance.ranking_weight = 0.05` does NOT have a paper citation — the patent doesn't recommend a weight in a multi-signal composite. Resolution per §B2 exception (a): match the FR-099–FR-105 active-tier weight band (0.04–0.05) which IS published per their respective specs (Page 1999, Katz 1953, Tarjan 1972, etc.). Code seed includes `# HEURISTIC: cross-tier match, no primary-source weight` per §B2 exception path. TPE auto-tuner refines automatically after 30-day burn-in.
- **A8 (hardware budget measured on target machine)**: estimates only in V1; measured numbers will land via `test_bench_passage_relevance.py` post-deploy. If the medium-batch benchmark exceeds 50 ms, follow-up slice ports the hot path to `passagesim.cpp` per Architecture Lane.
- **A1 §"Architecture Lane"**: V1 is pgvector + Python NumPy. Int8 FAISS quantization is in `## Pending`. The spec previously recommended Option A (FAISS); V1 ships Option B (pgvector) per simpler-first principle.

## Pending

Explicitly deferred to follow-up slices, per the masterplan's "stop after each group" discipline:

- **Int8-quantised passage FAISS index** (`faiss.IndexScalarQuantizer`). V1 uses pgvector(1024). Quantization saves ~75 % storage at the cost of ~1–2 % similarity error per the patent — worth doing once the signal is proven.
- **C++ extension `passagesim.cpp`** for batch passage similarity. Python NumPy is sufficient for V1 at the user's scale; C++ port follows when benchmarks indicate it.
- **Frontend settings card** (Group M of the masterplan).
- **Frontend suggestion-detail diagnostic block** (Group M).
- **Settings UI for the `passages_per_page` and `passage_words` knobs** — backend endpoint ships in V1; UI is pending.
- **`POST /api/settings/passage-relevance/rebuild-index/`** — manual trigger to re-chunk + re-embed everything. V1 builds the index incrementally as posts are imported / edited.

## Math-Fidelity Note

### Passage chunking (index time)

Let:

- `T` = `Post.clean_text` of a destination page (NOT `distilled_text` — the chunk source flipped in Group D.1)
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

- destination `Post.clean_text` — full BBCode-stripped body, for chunking at index time (post-Group-D.1 source — see "Group D.1 alignment" near the top)
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
- passage re-embedding is required when `Post.clean_text` changes (the new chunk source post-Group-D.1), adding ~5x the embedding computation cost vs page-level only — mitigated by Group D.2's `embedding_text_hash` discipline so unchanged pages skip the work;
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

## Phase 2 (Implementation) — Full-Coverage Passage Retrieval

This section details the Phase 2 extension of FR-053 to ensure full coverage without truncation, bounded memory using C++ extensions, and exhaustive passage chunking (implemented 2026-04-28).

### Academic Sources (Source of Truth)

- **OPQ (Optimised Product Quantisation):**
  - Jégou, Douze, Schmid 2011 TPAMI: "Product Quantization for Nearest Neighbor Search". DOI: `10.1109/TPAMI.2010.57`.
  - Ge, He, Ke, Sun 2013 TPAMI: "Optimized Product Quantization". DOI: `10.1109/TPAMI.2013.240`.
  - Microsoft Patent: **US 8,447,765 B2**.
- **MaxSim aggregation:**
  - Khattab, Zaharia 2020 SIGIR (ColBERT). arXiv:2004.12832.
  - Santhanam 2022 CIKM (PLAID). arXiv:2205.09707.
  - Google Patent: **US 9,940,367 B1** col 8 ll 5–32.
- **IVF (Inverted-File ANN):**
  - Sivic, Zisserman 2003 ICCV.
  - Jégou et al. 2010 CVPR (IVFADC).
  - Subramanya 2019 NeurIPS (DiskANN overflow path).
- **Chunk size (200 tokens + 25% overlap):**
  - Callan 1994 SIGIR §5.
  - Karpukhin 2020 EMNLP (DPR).
  - Lewis 2020 NeurIPS (RAG).
- **Pixie walks:**
  - Eksombatchai et al. 2018 WWW: "Pixie: A System for Recommending 3+ Billion Items to 200+ Million Users in Real-Time".

### Full-Coverage Architecture

- **Page-level embedding:** 32,000-char cap (BGE-M3's native 8,192-token capacity). Setting key: `passage_relevance.page_embedding_max_chars`.
- **Passage chunking:** 200-token windows, 25% overlap, no per-post cap. Setting key: `passage_relevance.passages_per_page_max = 0` (unlimited).
- **Host-sentence scanning:** Setting key `passage_relevance.host_scan_word_limit = 0` (unlimited). With OPQ on the destination side, host-side scoring is cheap enough to scan the entire host page.
- **Pixie random walks:** `graph_candidate.walk_steps_per_entity` at 5,000 default. Walks remain incremental via `PixieWalkVisit` last-write-wins upsert; they skip entities whose neighbourhood is unchanged.

### No-Duplicates Discipline

The system reuses existing dedup infra:
- **Same text re-embedded:** `ContentItem.embedding_text_hash` + `embedding_model_version` (Group D.2).
- **Same passage re-encoded:** `PassageEmbedding.embedding_text_hash` + `embedding_model_version`.
- **Same content from two sources:** `ContentItem.duplicate_of` (Group A.6).
- **Same URL crawled twice:** `CrawlerVisit` + `(normalized_url, content_hash)` upsert (Group D.5).
- **Old vector before overwrite:** `SupersededEmbedding` + 7-day retention.
- **Near-duplicate documents:** `ContentCluster` + pgvector cosine-distance HNSW.
- **OPQ codes for duplicate ContentItems:** Skip storing codes when `duplicate_of` is set; dereference to canonical at query time.
- **OPQ codes for unchanged passages:** Skip re-encoding when `embedding_text_hash` and `opq_codebook_version` match.

### Skip-On-Unchanged Discipline

If a full pipeline run encounters zero new content, zero work runs. Skip rules apply at every layer: Crawler, ContentItem upsert, Page-level embedding, Passage chunking, Passage embedding, OPQ encoding, OPQ codebook training, Pixie walks, and FAISS rebuild.

### Plain-English Summary

Passage-level retrieval now runs end-to-end. Every word of every forum post and WordPress page is split into ~200-word overlapping windows and stored as a compact 64-byte code. When a suggestion is scored, the system finds the best-matching window in milliseconds using a new C++ extension. Identical content is stored once. If the pipeline runs and nothing has changed, no work runs. The setting is on by default for the Recommended preset and can be turned off in the Settings panel. If the C++ extension fails to load for any reason, the system automatically falls back to the slower but always-correct Python path.

## Phase 2 Gate Justifications

- **Gate B (Slice):** Approved by operator. The slice extends FR-053 (no new signal), reuses existing dedup infra, and verifies the C++ kernel budget (≤512 MB RAM, ≤512 MB disk).
- **Gate A (quantemb.cpp):**
  - Architecture: OPQ training/encoding/decoding/asymmetric distance in C++.
  - Budget: ~5MB RAM for codebooks, well within 512MB limit. Disk for OPQ codes is ~450MB for 1M pages.
  - Floors: Parity ≤1e-4 vs NumPy, ≥3× faster than NumPy. Zero ASAN/UBSan errors.
- **Gate A (passagesim.cpp):**
  - Architecture: MaxSim aggregation via AVX2 FMA.
  - Budget: Near-zero persistent RAM (stateless), dynamic buffers ~10MB.
  - Floors: Parity ≤1e-6 vs NumPy (scoring hot path), ≥10× faster than NumPy per CPP-RULES.md §25. Zero ASAN/UBSan errors.
- **Gate A (ivf_index.cpp):**
  - Architecture: IVF clustering + asymmetric distance search.
  - Budget: ~16MB RAM for centroids + partition lists. Disk for IVF lists ~15MB.
  - Floors: Parity ≤1e-4 vs NumPy, ≥3× faster than NumPy, recall@100 ≥ 0.95. Zero ASAN/UBSan errors.
