# FR-048 — Topical Authority Cluster Density

**Status:** Pending
**Requested:** 2026-04-06
**Target phase:** TBD
**Priority:** Medium
**Depends on:** None (uses existing page embeddings already computed by the pipeline)

---

## Confirmation

- `FR-048` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no ranking signal currently measures the depth of the site's topical coverage around a destination page;
  - `FR-039` (entity salience) looks at individual salient terms on a single page, not the size of the topic cluster the page belongs to;
  - silo-aware ranking groups pages by URL path structure, not by semantic content similarity;
  - `FR-015` (slate diversity) diversifies the suggestion slate, but does not score destinations by topical cluster depth;
  - existing 1024-dim bge-m3 embeddings stored on `ContentItem` provide the input vectors needed for clustering with no additional embedding work.

## Current Repo Map

### Existing nearby signals

- `FR-039` entity salience
  - identifies important terms on a single destination page;
  - it does not measure how many other pages cover the same topic.

- Silo-aware ranking
  - groups pages by URL path prefix;
  - URL structure is an unreliable proxy for topical grouping — pages about "monitors" can live under `/reviews/`, `/guides/`, and `/deals/` but share a topic.

- `FR-015` slate diversity
  - spreads suggestions across dissimilar destinations;
  - it does not reward destinations that belong to deep topical clusters.

- `score_semantic` (w_semantic)
  - measures pairwise similarity between source and destination;
  - it does not measure how many other pages are similar to the destination.

### Gap this FR closes

The repo cannot currently prefer destinations where the site has deep topical authority. A page about "mechanical keyboard switches" is a stronger link target when the site has 30 other pages about keyboards than when it is the only keyboard page. Search engines reward sites with topical depth, and internal links into deep clusters reinforce that depth signal.

## Source Summary

### Concept: Topical Authority and Hub/Authority Scoring

Plain-English read:

- search engines give ranking boosts to sites that demonstrate deep expertise on a topic;
- topical authority is measured by how many quality pages a site has within a subject cluster;
- linking into topically dense clusters reinforces the site's authority signal to crawlers;
- Kleinberg's HITS algorithm (1999) formalized the idea that pages in dense, interlinked clusters serve as authoritative hubs.

Repo-safe takeaway:

- destinations in large semantic clusters should receive a modest boost;
- cluster size is a proxy for the site's topical depth around that destination;
- the math is clustering existing embeddings and counting cluster members — no new data source needed.

### Method: HDBSCAN density-based clustering

Plain-English read:

- HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise) finds clusters of varying density in high-dimensional data;
- unlike k-means, it does not require specifying the number of clusters in advance;
- it labels outlier points as noise rather than forcing them into a cluster;
- it works well with embedding vectors where topic boundaries are not uniform.

Repo-safe takeaway:

- HDBSCAN is the right fit because the number of topics on a site is unknown and varies;
- noise-labeled pages (unique, off-topic content) naturally receive the neutral fallback score;
- the `min_cluster_size` parameter controls the minimum number of pages required to form a recognized topic.

### Concept: Majestic Topical Trust Flow

Plain-English read:

- Majestic's Topical Trust Flow categorizes web pages into topical categories and measures trust within each topic;
- pages with many inbound links from topically related sources score higher;
- the key insight is that topical concentration of links matters, not just raw link count.

Repo-safe takeaway:

- cluster density is the internal-link analogue of topical trust flow;
- destinations in deep clusters benefit from concentrated internal topical authority.

## Plain-English Summary

Simple version first.

Search engines trust sites that go deep on a topic.
A site with 30 pages about keyboards is more authoritative on keyboards than a site with 1.

FR-048 groups all pages by topic using their existing embeddings.
Destinations in big topic groups get a small boost.
Destinations that are loners (the only page on their topic) stay neutral.

Example:

- The site has 25 pages about gaming peripherals (keyboards, mice, monitors, chairs).
- The site has 2 pages about gardening tools.
- FR-048 boosts a link to "Best Mechanical Keyboards" (cluster of 25) over a link to "Garden Hose Reviews" (cluster of 2), all else being equal.

## Problem Statement

Today the ranker scores destinations by relevance, authority, engagement, and many other signals — but none of them measure whether the destination sits within a deep topical cluster on the site.

Two equally relevant destinations can differ dramatically in how much topical authority the site has around them. FR-048 adds a signal so the ranker can prefer destinations where internal linking will reinforce the site's recognized expertise.

## Goals

FR-048 should:

- cluster all site pages by topic using existing bge-m3 embeddings;
- compute a per-page cluster density score based on how large the page's topic cluster is;
- produce a bounded suggestion-level score that gently boosts destinations in deep clusters;
- stay neutral for noise/outlier pages and for sites with too few pages to cluster meaningfully;
- recompute clusters periodically (daily or per-pipeline-run), not on every suggestion;
- fit the repo without adding new embedding models or external data sources.

## Non-Goals

FR-048 does not:

- replace or modify silo-aware ranking (URL-based grouping remains separate);
- replace or modify FR-039 entity salience (single-page term analysis remains separate);
- create or modify the topical taxonomy — it discovers clusters automatically from embeddings;
- require manual topic labeling by the operator;
- use external topic classification APIs.

## Math-Fidelity Note

### Input data

Use existing `ContentItem.embedding` vectors (1024-dim bge-m3).

Let:

- `N` = total number of content items with embeddings
- `E` = N × 1024 embedding matrix

### Step 1 — dimensionality reduction (optional, for performance)

When `N > 5000`, reduce dimensionality before clustering to improve HDBSCAN performance:

```text
E_reduced = UMAP(E, n_components=50, metric='cosine')
```

When `N ≤ 5000`, use raw embeddings with cosine distance directly.

### Step 2 — HDBSCAN clustering

```text
labels = HDBSCAN(E_reduced, min_cluster_size=min_cluster_size, metric='euclidean')
```

Where:

- `labels[i]` = cluster ID for page `i`, or `-1` if the page is noise (outlier)
- `min_cluster_size` = minimum pages required to form a topic cluster

Recommended default:

- `min_cluster_size = 5`

### Step 3 — compute cluster sizes

For each cluster `c`:

```text
cluster_size(c) = count of pages where labels[i] == c
```

Also compute:

```text
max_cluster_size = max(cluster_size(c))  for all c
                   c
```

### Step 4 — log-normalized density score

For a destination page `d` in cluster `c`:

```text
density_raw(d) = log(cluster_size(c)) / log(max(max_cluster_size, 2))
```

The `log` transform prevents huge clusters from dominating. A cluster of 100 pages scores only 2x a cluster of 10, not 10x.

The `max(..., 2)` in the denominator prevents division by zero or log(1) = 0 when all clusters have size 1.

For noise pages (`labels[d] == -1`):

```text
density_raw(d) = 0.0
```

### Step 5 — bounded score

```text
score_topical_cluster = 0.5 + 0.5 * min(1.0, density_raw(d))
```

Score range:

- `0.5` = noise page or smallest viable cluster
- `1.0` = page belongs to the largest topic cluster on the site

Neutral fallback:

```text
score_topical_cluster = 0.5
```

Used when:

- feature disabled;
- site has fewer than `min_site_pages` total pages with embeddings;
- clustering has not been computed yet;
- page has no embedding.

### Step 6 — freshness decay (optional)

If cluster assignments are stale (computed more than `max_staleness_days` ago):

```text
staleness_factor = max(0.0, 1.0 - (days_since_computation / max_staleness_days))
score_topical_cluster_decayed = 0.5 + staleness_factor * (score_topical_cluster - 0.5)
```

This gradually blends toward neutral as cluster data ages, preventing stale cluster assignments from influencing ranking indefinitely.

Recommended default:

- `max_staleness_days = 14`

### Ranking hook

```text
score_topical_cluster_component =
  max(0.0, min(1.0, 2.0 * (score_topical_cluster - 0.5)))
```

```text
score_final += topical_cluster.ranking_weight * score_topical_cluster_component
```

Default:

- `ranking_weight = 0.0`

## Scope Boundary Versus Existing Signals

FR-048 must stay separate from:

- `FR-039` entity salience
  - FR-039 identifies important terms on a single page;
  - FR-048 measures the size of the topic cluster the page belongs to.

- Silo-aware ranking
  - Silo uses URL path structure to group pages;
  - FR-048 uses semantic embedding similarity to group pages.

- `FR-015` slate diversity
  - FR-015 diversifies the suggestion list;
  - FR-048 scores individual destinations by their cluster depth.

- `score_semantic` (w_semantic)
  - w_semantic measures pairwise similarity between source and destination;
  - FR-048 measures how many other pages are similar to the destination (cluster size).

Hard rule:

- FR-048 must not mutate embeddings, `distilled_text`, or other feature caches.

## Inputs Required

FR-048 v1 can use:

- `ContentItem.embedding` (existing 1024-dim bge-m3 vectors)
- `ContentItem.url` (for diagnostics / cluster labeling)
- `ContentItem.title` (for diagnostics / cluster labeling)

Explicitly disallowed in v1:

- external topic classification APIs;
- manual topic labels or operator-defined taxonomy;
- re-embedding pages with a different model;
- real-time clustering on every suggestion request.

## Data Model Plan

Add to `ContentItem`:

- `topical_cluster_id` — integer cluster label assigned by HDBSCAN (-1 for noise)
- `topical_cluster_score` — cached float score for this page's cluster density

Add to `Suggestion`:

- `score_topical_cluster`
- `topical_cluster_diagnostics`

Add new model:

- `TopicalCluster` — stores cluster metadata: `cluster_id`, `size`, `density_score`, `sample_titles` (JSON, top 5 page titles for human-readable labeling), `computed_at`

## Settings And Feature-Flag Plan

Recommended keys:

- `topical_cluster.enabled`
- `topical_cluster.ranking_weight`
- `topical_cluster.min_cluster_size`
- `topical_cluster.min_site_pages`
- `topical_cluster.max_staleness_days`
- `topical_cluster.fallback_value`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `min_cluster_size = 5`
- `min_site_pages = 20`
- `max_staleness_days = 14`
- `fallback_value = 0.5`

## Diagnostics And Explainability Plan

Diagnostics should include:

- `cluster_id`
- `cluster_size`
- `max_cluster_size`
- `density_raw`
- `sample_cluster_pages` (cap 5 titles from the same cluster)
- `days_since_computation`
- `staleness_factor`
- `fallback_state`

Plain-English helper text:

- "Topical cluster density boosts destinations in deep topic areas where the site has many related pages, reinforcing topical authority signals to search engines."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

The HDBSCAN clustering step runs infrequently (daily) and Python with scikit-learn is fast enough. The native path is only needed for the per-suggestion scoring loop.

Add a native batch scorer that reads cached `topical_cluster_score` values and applies the ranking hook arithmetic across all suggestions.

Suggested file:

- `backend/extensions/topicalcluster.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/topical_cluster.py`

The Python and C++ paths must produce the same bounded scores for the same cluster assignments.

### Visibility requirement

Expose:

- native enabled / fallback enabled;
- why fallback is active;
- whether native batch scoring is materially faster;
- when clusters were last computed and how many clusters were found.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/topical_cluster.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/topicalcluster.cpp`

## Verification Plan

Later implementation must verify at least:

1. pages in large clusters outrank pages in tiny clusters when other signals are equal;
2. noise pages (HDBSCAN label -1) receive the neutral 0.5 fallback;
3. sites with fewer than `min_site_pages` pages receive neutral fallback for all pages;
4. `ranking_weight = 0.0` leaves ranking unchanged;
5. log normalization prevents huge clusters from having disproportionate influence;
6. staleness decay blends toward neutral as cluster data ages;
7. C++ and Python paths produce identical scores;
8. diagnostics explain which cluster a page belongs to and why it scored high, low, or neutral.
