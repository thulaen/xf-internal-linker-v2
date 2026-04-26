# FR-021 - Graph-Based Link Candidate Generation (Pixie Random Walk + Instagram Value Scoring)

## Confirmation

- `FR-021` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 24`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - a `ContentItem` model with cross-source support already exists;
  - entity extraction does not yet exist as a standalone service;
  - an embedding-based candidate retrieval step already exists inside the pipeline;
  - a multi-signal scoring layer already exists;
  - the Python analytics worker (`backend/apps/analytics/services/`) computes and stores content-value scores (replaces the former R analytics service and the decommissioned-2026-04 C# Analytics Worker);
  - `SearchMetric` already stores daily coarse GA4 / GSC traffic data per content item;
  - no bipartite article-entity graph or random-walk candidate layer exists yet.

## Current Repo Map

### Existing pipeline plumbing

- `backend/apps/pipeline/`
  - candidate retrieval is driven by embedding similarity today;
  - scoring applies multiple bounded signal layers (FR-006 through FR-015);
  - the pipeline stores a snapshot of scores per run in `PipelineRunSnapshot`.
- `backend/apps/content/models.py`
  - `ContentItem` — canonical content node (XenForo thread/resource, WP post/page);
  - `ScopeItem`, `SiloGroup`, `ContentCluster` — structural groupings.
- `backend/apps/suggestions/models.py`
  - `Suggestion` — stores scored candidate pairs plus per-signal diagnostics.
- `backend/apps/analytics/models.py`
  - `SearchMetric` — daily coarse GSC / GA4 metrics by content item;
  - `ImpactReport` — before/after comparison rows for applied suggestions.
- `backend/apps/analytics/services/` (Python; replaced the decommissioned `services/http-worker/.../HttpWorker.Analytics/` in 2026-04)
  - Content-value scoring uses Django ORM queries + numpy / scipy.stats; batch writes via the ORM.
  - Charts are rendered by D3.js in the Angular frontend, not server-side.

### Existing signal scores on `ContentItem` or `Suggestion`

- `march_2026_pagerank_score` — weighted authority (FR-006)
- `score_link_freshness` — link freshness (FR-007)
- `score_phrase_relevance` — phrase matching (FR-008)
- `score_learned_anchor_corroboration` — learned anchors (FR-009)
- `score_rare_term_propagation` — rare-term propagation (FR-010)
- `score_field_aware_relevance` — field-aware relevance (FR-011)

### Gaps

- No entity extraction layer — entities must be introduced here.
- No bipartite graph storage layer for articles and entities.
- No random-walk engine.
- No value-model scoring combining relevance + traffic.

## Workflow Drift / Doc Mismatch Found During Inspection

- `docs/v2-master-plan.md` does not reference graph-based candidate generation; this is a new architectural layer.
- The current pipeline retrieves candidates only by embedding similarity; high-traffic or entity-rich pages that embed differently from the source may be systematically missed.
- R analytics outputs are not yet wired into the Django pipeline scoring layer.

## Source Summary

### External research used

- Pinterest Pixie paper: [arXiv 1711.07601](https://arxiv.org/abs/1711.07601)
- Pinterest Engineering Blog — Introducing Pixie
- Instagram Feed Recommendations — Meta Transparency
- Meta Engineering Blog — Scaling Instagram Explore Recommendations

### Key facts extracted

- Pixie builds a bipartite graph, does a biased random walk from query nodes, and counts visits to surface the most-connected candidates.
- Early stopping halves the steps needed while preserving quality.
- Multi-hit boosting surfaces candidates that appear at the intersection of multiple query signals, not just one.
- Instagram's value model is a weighted sum: `score = Σ(weight_i × P(action_i))` where each action is a predicted user behavior.
- Weights are tunable; in our case we replace predicted social actions with measured content signals.
- Both systems use a multi-stage funnel: generate broadly, then score and narrow.

### What was clear

- The article-entity graph will be far smaller than Pinterest's (thousands of nodes, not billions).
- Storage impact is well within 20 GB headroom for a typical site.
- The Pixie walk and the Instagram value formula are both implementable without any ML model dependency — they are graph math and weighted arithmetic.
- The R analytics service already produces the content-value scores that feed the value model.

### What remained ambiguous

- Whether entity extraction should use spaCy NER, keyword extraction (YAKE / KeyBERT), or a simpler noun-phrase extractor.
- Whether the graph should be rebuilt on every sync or rebuilt incrementally.
- How many random-walk steps are right for a small graph (Pinterest used 100,000 for billions of nodes; a small site may need far fewer).

## Problem Definition

Simple version first.

Right now the pipeline finds candidate target pages only by asking "how similar does this page embed to the source?" That misses pages that are topically related but embed differently — for example a high-traffic evergreen page written in a slightly different register.

The fix is to add a second candidate channel:

1. Build a bipartite knowledge graph — Articles on one side, Entities (topics/keywords) on the other, edges linking each article to the entities it contains.
2. Run a Pixie-style biased random walk from the source article through shared entities to reach candidate destination articles.
3. Score those candidates with an Instagram-style value model — a weighted sum of relevance signals and real traffic data from R analytics / SearchMetric.
4. Merge graph-walk candidates with existing embedding candidates before the main scoring layer.

The graph walk finds candidates the embedding misses.
The value model ranks candidates by what actually matters to this site: topical fit plus real page traffic.

## Graph Architecture

### Node types

- `ArticleNode` — one node per `ContentItem`.
- `EntityNode` — one node per extracted entity (keyword, named entity, or topic tag).

### Edge types

- `ArticleEntityEdge` — links an `ArticleNode` to an `EntityNode` it contains.
  - weight: entity prominence in the article (TF-IDF-style, bounded 0–1).

### Storage

Add a new backend app: `backend/apps/knowledge_graph/`

Models:

- `EntityNode`
  - `entity_id` (UUID)
  - `surface_form` (CharField, indexed)
  - `canonical_form` (CharField, indexed)
  - `entity_type` (CharField: keyword / named_entity / topic_tag)
  - `created_at`, `updated_at`

- `ArticleEntityEdge`
  - `content_item` (ForeignKey → ContentItem)
  - `entity` (ForeignKey → EntityNode)
  - `weight` (FloatField, 0.0–1.0)
  - `extraction_version` (CharField)
  - `created_at`

The full graph for a typical site fits in a few hundred megabytes in-memory as a sparse adjacency structure.
It fits in a few MB in the database.

## Entity Extraction

### First-pass approach

Use a simple, dependency-free extractor for the first pass:

- Split `ContentItem.distilled_text` into sentences.
- Extract noun phrases and known named entities using spaCy `en_core_web_sm` (already likely available given the embedding stack).
- Score each entity by raw frequency normalized by document length (bounded TF-IDF approximation).
- Keep the top N entities per article (default: 20, configurable).
- Store canonical lowercase forms for deduplication.

### Extraction task

- `build_entity_graph` Celery task:
  - iterates all `ContentItem` rows;
  - extracts entities;
  - upserts `EntityNode` and `ArticleEntityEdge` rows;
  - stores `extraction_version` per edge so stale edges can be pruned.

- Trigger:
  - after each content sync;
  - on-demand from settings/UI;
  - scheduled alongside the main pipeline run.

## Pixie Random Walk Algorithm

### Inputs

- `query_article` — the source `ContentItem` for which we want candidate links.
- `query_entities` — the entity nodes linked to `query_article`, weighted by edge weight.

### Walk process

1. Start a visit-count accumulator over all `ArticleNode` instances.
2. For each `query_entity`, weighted by its edge weight to `query_article`:
   a. Begin at `query_entity`.
   b. Alternate: article neighbor → entity neighbor → article neighbor.
   c. At each step, choose the next neighbor with probability proportional to edge weight (biased walk).
   d. Increment the visit count for every `ArticleNode` visited.
3. Apply multi-hit boost: if a candidate was reached from multiple `query_entities`, apply a non-linear boost (default: `sqrt(visit_count)`).
4. Apply early stopping: stop when at least `min_stable_candidates` (default: 50) articles have each been visited at least `min_visit_threshold` (default: 3) times.
5. Return the top-K articles by boosted visit count (default K: 100) excluding the source article itself.

### Walk parameters (all configurable)

- `walk_steps_per_entity` (default: 1000)
- `min_stable_candidates` (default: 50)
- `min_visit_threshold` (default: 3)
- `top_k_candidates` (default: 100)
- `multi_hit_boost_fn` (default: `sqrt`)

### Candidate merging

- Merge Pixie candidates with existing embedding candidates.
- Deduplicate by `content_item_id`.
- Mark each candidate's origin: `embedding`, `graph_walk`, or `both`.
- Pass merged set to the main scoring layer.

## Instagram-Style Value Model

### Purpose

Rank the merged candidate pool before the main multi-signal scoring layer applies.
This is a pre-ranking pass, not a replacement for existing signal scores.

### Formula

```
value_score = (
    w_relevance   × relevance_signal
  + w_traffic     × traffic_signal
  + w_freshness   × freshness_signal
  + w_authority   × authority_signal
  - w_penalty     × penalty_signal
)
```

All signals are bounded [0, 1].
All weights are configurable via settings API.

### Signal definitions

- `relevance_signal`
  - source: embedding cosine similarity from existing retrieval layer;
  - default weight: `0.4`.

- `traffic_signal`
  - source: normalized `SearchMetric` clicks + impressions per content item;
  - normalized against the site's 90-day traffic distribution;
  - falls back to `0.5` when no traffic data exists;
  - default weight: `0.3`.
  - Note: R analytics `compute_logic.R` already produces a content-value score; this column feeds `traffic_signal` directly when available.

- `freshness_signal`
  - source: `ContentItem.link_freshness_score` (FR-007);
  - default weight: `0.1`.

- `authority_signal`
  - source: `ContentItem.march_2026_pagerank_score` (FR-006);
  - default weight: `0.1`.

- `penalty_signal`
  - source: existing-link block flag, cross-silo strict-block flag;
  - value is `1.0` if blocked, `0.0` otherwise;
  - default weight: `0.5`.
  - Blocked candidates still pass through but sink to the bottom of the pre-ranking pass.

### Value model settings API

- `GET/PUT /api/settings/value-model/`
- Fields:
  - `enabled` (bool, default: true)
  - `w_relevance` (float, default: 0.4)
  - `w_traffic` (float, default: 0.3)
  - `w_freshness` (float, default: 0.1)
  - `w_authority` (float, default: 0.1)
  - `w_penalty` (float, default: 0.5)
  - `traffic_lookback_days` (int, default: 90)
  - `traffic_fallback_value` (float, default: 0.5)
  - `walk_steps_per_entity` (int, default: 1000)
  - `min_stable_candidates` (int, default: 50)
  - `min_visit_threshold` (int, default: 3)
  - `top_k_candidates` (int, default: 100)
  - `top_n_entities_per_article` (int, default: 20)
  - `entity_extraction_version` (str, read-only)
  - `graph_last_built_at` (datetime, read-only)
  - `graph_article_count` (int, read-only)
  - `graph_entity_count` (int, read-only)
  - `graph_edge_count` (int, read-only)

## Pipeline Integration

### Where this fits in the pipeline

```
[Sync: XF + WP content arrives]
        ↓
[Entity Extraction → Knowledge Graph build]
        ↓
[Candidate Retrieval]
  ├── Embedding similarity (existing)
  └── Pixie random walk (new)
        ↓
[Candidate Merge + Deduplication]
        ↓
[Instagram Value Pre-Ranking]  ← new
        ↓
[Multi-Signal Scoring (FR-006 → FR-015)]
        ↓
[Diversity Reranking (FR-015)]
        ↓
[Suggestions stored]
```

### Suggestion model additions

Add to `Suggestion`:

- `candidate_origin` (CharField: `embedding`, `graph_walk`, `both`)
- `score_value_model` (FloatField, null/blank)
- `value_model_diagnostics` (JSONField, default dict)

`value_model_diagnostics` shape:

```json
{
  "relevance_signal": 0.82,
  "traffic_signal": 0.61,
  "freshness_signal": 0.74,
  "authority_signal": 0.55,
  "penalty_signal": 0.0,
  "weights": {
    "w_relevance": 0.4,
    "w_traffic": 0.3,
    "w_freshness": 0.1,
    "w_authority": 0.1,
    "w_penalty": 0.5
  },
  "value_score": 0.712,
  "graph_visit_count": 14,
  "graph_multi_hit_boost": 3.74,
  "traffic_data_source": "search_metric",
  "traffic_fallback_used": false
}
```

## Settings UI

Add a new settings card: **Graph Candidate Generation & Value Scoring**

Controls:

- Enable / disable graph candidate generation.
- Enable / disable value model pre-ranking.
- Walk parameters (steps, K, min-stable, entity count).
- Weight sliders for value model signals.
- Traffic lookback window.
- "Rebuild Graph Now" button with progress indicator.
- Graph stats: article count, entity count, edge count, last built timestamp.
- "Preview walk candidates" for a specific source URL (debug/power-user feature).

## Graph Build Task

- `build_knowledge_graph` Celery task:
  - runs after each sync or on demand;
  - extracts entities for all `ContentItem` rows;
  - upserts `EntityNode` and `ArticleEntityEdge`;
  - prunes stale edges from previous extraction versions;
  - writes `graph_last_built_at` and stats to `AppSetting`.

- Estimated runtime for a typical site (10,000 articles): under 2 minutes.

## Review UI Additions

On the Suggestion review detail view, add:

- `Candidate origin`: embedding / graph walk / both.
- `Value model score`: with expandable diagnostics showing each signal contribution.
- `Graph visit count` and `multi-hit boost` when origin includes graph walk.

## Diagnostics

Add a graph health diagnostic endpoint:

- `GET /api/knowledge-graph/stats/`
  - article count
  - entity count
  - edge count
  - last built timestamp
  - extraction version
  - coverage percentage (articles with at least one entity)
  - top 20 entities by article coverage

## Test Plan

### Backend tests

- Entity extraction produces expected entities from test corpus.
- `ArticleEntityEdge` weights are bounded [0, 1].
- Random walk visits more articles that share more entities with the source.
- Multi-hit boost amplifies intersection candidates correctly.
- Early stopping fires before `walk_steps_per_entity` when stability is reached.
- Candidate merge deduplicates correctly and preserves origin tags.
- Value model score is bounded [0, 1] given bounded inputs.
- Missing traffic data falls back to configured default.
- Penalty signal sinks blocked candidates without removing them.
- Settings API reads and writes all configurable fields.

### Frontend tests

- Settings card renders graph stats and controls.
- Rebuild graph button shows progress and updates stats on completion.
- Review detail shows candidate origin and value model diagnostics.

### Manual verification

- Run a full pipeline on a real sync snapshot.
- Confirm some suggestions have `candidate_origin = graph_walk`.
- Confirm some suggestions have `candidate_origin = both`.
- Confirm `value_model_diagnostics` is populated.
- Confirm high-traffic pages surface as candidates for topically related source articles even if embedding similarity was low.

## Acceptance Criteria

- The knowledge graph is built and rebuilt correctly after each sync.
- Pixie random walk produces candidates that are not in the top-K embedding results.
- Merged candidate set correctly tags origin.
- Value model pre-ranking uses real traffic data from `SearchMetric` or R analytics output.
- Existing scoring signals (FR-006 to FR-015) still apply unchanged after the pre-ranking pass.
- All new parameters are configurable and documented in the settings UI.
- Suggestion diagnostics show value model contribution.
- Disk footprint for the graph is well under 1 GB for a typical site.

## Out-of-Scope Follow-Up

- Graph-based embedding propagation (using graph structure to improve embeddings themselves).
- Community detection or automatic silo discovery from the entity graph.
- Named entity resolution against external knowledge bases (Wikipedia, Wikidata).
- Real-time incremental graph updates per article edit.
- Automatic weight tuning for the value model (that belongs to `FR-018`).
