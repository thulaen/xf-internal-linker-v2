# FR-064 - Spectral Relational Clustering

## Confirmation

- **Backlog confirmed**: `FR-064 - Spectral Relational Clustering` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No multi-relational clustering exists in the current system. The closest mechanism is planned HDBSCAN clustering (FR-048), which clusters pages in a single embedding space. FR-064 simultaneously clusters pages, anchor texts, and query patterns by computing leading eigenvectors of combined relation matrices -- a fundamentally different approach that captures three-way relationships.
- **Repo confirmed**: Anchor text data is stored in `ExistingLink` model, query data is available from GSC imports, and page embeddings are already indexed. These provide the three relation types needed for the joint Laplacian.

## Current Repo Map

### Clustering already available or planned

- `backend/apps/pipeline/services/clustering.py`
  - Near-duplicate clustering (FR-014) uses cosine similarity thresholds between page embeddings. Single-type, single-relation.

- `FR-048 Topical Authority Cluster Density` (planned)
  - HDBSCAN on page embeddings. Still single-type (pages only) and single-relation (embedding distance).

### Relation data already available

- `backend/apps/content/models.py`
  - `ContentItem` with `distilled_text`, `embedding`, `url`, `silo`.
  - Provides the page entities for the P (pages) dimension.

- `backend/apps/graph/models.py`
  - `ExistingLink` with `anchor_text` connecting source and destination pages.
  - Provides the A (anchor phrases) dimension.

- `backend/apps/search_console/` (GSC imports)
  - Query strings and the pages they map to.
  - Provides the Q (queries) dimension.

## Source Summary

### Patent: US8185481B2 -- Spectral Clustering for Multi-Type Relational Data (SUNY, 2012)

**Plain-English description of the patent:**

The patent describes a method for clustering objects of multiple types simultaneously using spectral methods. Instead of clustering pages alone, it builds relation matrices that connect different entity types (e.g., pages-to-anchors, pages-to-queries) and computes a joint spectral embedding that captures cross-type relationships. The leading eigenvectors of the combined Laplacian matrix reveal natural groupings that span all entity types.

**Repo-safe reading:**

The patent handles arbitrary numbers of entity types and relations. This repo uses exactly two relation types: page-anchor and page-query. The joint Laplacian is a weighted average of the two normalised Laplacians, solved via sparse eigendecomposition.

**What is directly supported by the patent:**

- building relation matrices between different entity types;
- computing normalised Laplacians per relation;
- combining Laplacians into a joint matrix;
- spectral embedding via leading eigenvectors;
- clustering in the spectral embedding space.

**What is adapted for this repo:**

- two relation types (page-anchor, page-query) instead of arbitrary;
- equal weighting (0.5 each) for the joint Laplacian;
- K-Means (K=32) on the spectral embedding for final cluster assignment;
- cluster labels stored per page and used as a grouping signal for silo analysis.

## Plain-English Summary

Simple version first.

Imagine you have a set of web pages, a set of anchor text phrases used to link between them, and a set of search queries that lead to them. Each of these lives in its own world, but they are connected:

- Page A uses anchor "SEO audit tool" to link to Page B.
- Page B appears in search results for query "site audit software."
- Page C also appears for "site audit software" and uses anchor "technical SEO checker."

These connections reveal that pages A, B, and C belong to the same topic cluster -- even if their raw content embeddings are not very similar. The anchor texts and queries act as bridges that reveal hidden topic relationships.

FR-064 builds two connection matrices (pages-to-anchors, pages-to-queries) and mathematically combines them into a single "joint" matrix. It then finds the natural groupings in this combined space using spectral decomposition (finding the matrix's eigenvectors). The result is a set of cluster labels that reflect three-way relationships: pages that share anchor phrases AND query patterns get clustered together.

This is richer than HDBSCAN (which only looks at page embeddings) because it incorporates link structure and search behaviour into the clustering decision.

## Problem Statement

Current and planned clustering methods operate on a single type of relationship:

1. **Near-duplicate clustering (FR-014)**: cosine similarity between page embeddings. Catches content copies but not thematic groupings.
2. **HDBSCAN (FR-048)**: density-based clustering in embedding space. Captures topical proximity but misses structural relationships encoded in anchor texts and search queries.

Neither captures the multi-relational structure of the site: two pages might be distant in embedding space but closely related through shared anchor phrases and overlapping query sets. FR-064 captures these cross-type relationships through joint spectral decomposition.

## Goals

FR-064 should:

- build sparse binary relation matrices R1 (pages x anchors) and R2 (pages x queries);
- compute symmetrised adjacency matrices A1 = R1*R1^T and A2 = R2*R2^T;
- compute normalised Laplacians for each relation;
- form the joint Laplacian as a weighted average (0.5 * L1 + 0.5 * L2);
- compute the top d=16 eigenvectors of the joint Laplacian via sparse eigendecomposition;
- embed each page as a 16-dimensional vector from those eigenvectors;
- cluster pages into K=32 clusters using K-Means on the spectral embedding;
- store cluster labels per page for use by silo analysis and link scoping;
- recompute clusters periodically (default: weekly) via Celery task;
- fit within ~300 MB RAM during computation (discardable after clustering).

## Non-Goals

FR-064 does not:

- replace HDBSCAN clustering (FR-048) -- it provides a complementary multi-relational view;
- modify page embeddings or text content;
- produce a ranking score directly -- the cluster labels are used by other systems;
- require real-time computation (batch process only);
- handle more than two relation types in v1;
- cluster anchor texts or queries themselves (only pages are assigned cluster labels);
- implement production code in the spec pass.

## Math-Fidelity Note

### Relation matrix construction

```text
R_1 in {0,1}^{P x A}     P = number of pages, A = number of unique anchor phrases
  R_1(i, j) = 1 if page i uses anchor phrase j in any outgoing link

R_2 in {0,1}^{P x Q}     Q = number of unique query strings
  R_2(i, k) = 1 if page i appears in search results for query k
```

### Symmetrised adjacency matrices

```text
A_1 = R_1 * R_1^T in R^{P x P}
  A_1(i, j) = number of anchor phrases shared between pages i and j

A_2 = R_2 * R_2^T in R^{P x P}
  A_2(i, j) = number of queries shared between pages i and j
```

### Normalised Laplacians

```text
D_k = diag(row sums of A_k)     [degree matrix for relation k]

L_k = I - D_k^{-1/2} * A_k * D_k^{-1/2}
```

The normalised Laplacian `L_k` has eigenvalues in [0, 2]. Small eigenvalues correspond to groups of pages that are tightly connected through relation k.

### Joint Laplacian

```text
L_joint = 0.5 * L_1 + 0.5 * L_2
```

Equal weighting treats anchor-based and query-based relationships as equally important. This can be adjusted in future versions based on clustering quality metrics.

### Spectral embedding

```text
Compute top d=16 eigenvectors {v_1, ..., v_16} of L_joint
  using scipy.sparse.linalg.eigsh (Lanczos method)

Embed each page i: e_i = [v_1(i), v_2(i), ..., v_16(i)] in R^16
```

The eigenvectors corresponding to the smallest eigenvalues capture the coarsest cluster structure. Using d=16 dimensions captures 16 levels of hierarchical grouping.

### Final clustering

```text
Run K-Means(K=32, n_init=10) on {e_i}_{i=1..P}
Output: cluster_id(i) in {0, 1, ..., 31} per page
```

K=32 clusters balances granularity (enough clusters to capture meaningful topic groups) against interpretability (few enough for operators to understand).

### Computational cost

```text
Sparse matrix construction: O(nnz(R_1) + nnz(R_2))
Symmetrised product: O(P * max_degree^2) per relation
Eigendecomposition: O(P * d^2) via Lanczos (sparse)
K-Means: O(P * K * d * n_init)

RAM: sparse matrices ~150 MB + eigen workspace ~150 MB = ~300 MB peak (discardable)
```

## Scope Boundary Versus Existing Signals

FR-064 must stay separate from:

- `Near-duplicate clustering (FR-014)`
  - near-dup uses cosine similarity between page embeddings (content-based);
  - FR-064 uses multi-relational spectral decomposition (structure-based);
  - completely different inputs and algorithms.

- `HDBSCAN topical authority (FR-048)`
  - HDBSCAN clusters by embedding density (single-type, single-relation);
  - FR-064 clusters by anchor and query co-occurrence (multi-type, multi-relation);
  - different data sources, different mathematical framework.

- `Semantic similarity (score_semantic)`
  - semantic similarity compares individual document pairs;
  - FR-064 discovers global grouping structure across the entire site;
  - different granularity and purpose.

Hard rule: FR-064 must not modify any page embedding, any text field, or any existing cluster assignment. It produces its own independent cluster labels stored in a separate field.

## Inputs Required

FR-064 uses only data already available:

- `ExistingLink.anchor_text` -- for the page-anchor relation matrix R1
- GSC query data (page-to-query mappings) -- for the page-query relation matrix R2
- `ContentItem.id` -- page identifiers for matrix row indices

Explicitly disallowed inputs:

- page embeddings (those are for HDBSCAN)
- click data or engagement metrics (those are for FR-061)
- any data not already stored in the database

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `spectral_rc.enabled`
- `spectral_rc.num_clusters`
- `spectral_rc.spectral_dims`
- `spectral_rc.anchor_weight`
- `spectral_rc.query_weight`
- `spectral_rc.recompute_interval_days`

Defaults:

- `enabled = true`
- `num_clusters = 32`
- `spectral_dims = 16`
- `anchor_weight = 0.5`
- `query_weight = 0.5`
- `recompute_interval_days = 7`

Bounds:

- `8 <= num_clusters <= 128`
- `4 <= spectral_dims <= 64`
- `0.0 <= anchor_weight <= 1.0`
- `0.0 <= query_weight <= 1.0` (anchor_weight + query_weight must equal 1.0)
- `1 <= recompute_interval_days <= 30`

### Feature-flag behavior

- `enabled = false`
  - skip clustering entirely
  - store `spectral_cluster_id = null` on all pages
  - store `spectral_rc_state = disabled`
- `enabled = true`
  - compute clusters and store labels per page
  - cluster labels available for silo analysis and link scoping

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `SpectralRCDiagnostics` (stored system-wide, not per-suggestion)

Required fields:

- `spectral_rc_state` -- `computed`, `disabled`, `insufficient_data`
- `num_pages_clustered` -- total pages assigned cluster labels
- `num_clusters_formed` -- actual cluster count (may be < K if some clusters are empty)
- `cluster_size_distribution` -- histogram of cluster sizes
- `eigenvalue_spectrum` -- top 16 eigenvalues (for operator to assess cluster separability)
- `silhouette_score` -- mean silhouette coefficient (clustering quality metric)
- `relation_coverage` -- `{anchors: N pages with anchor data, queries: N pages with query data}`
- `computation_time_seconds` -- wall clock time for the clustering run
- `model_version` -- timestamp of the computation

Per-page fields:

- `ContentItem.spectral_cluster_id` -- integer cluster label
- `ContentItem.spectral_embedding` -- 16-dim vector (optional, for debugging)

Plain-English review helper text should say:

- `Spectral clusters group pages by shared anchor phrases and search query patterns.`
- `Pages in the same cluster are linked by similar language and appear for similar searches.`
- `This captures relationships invisible to content-only clustering.`

## Storage / Model / API Impact

### Content model

Add:

- `spectral_cluster_id: IntegerField(null=True, blank=True, db_index=True)`

### System diagnostics

- `SpectralRCDiagnostics` stored as a JSON record in `AppSetting` key `spectral_rc.diagnostics`

### PipelineRun snapshot

Add FR-064 settings and cluster version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/spectral-rc/`
- `PUT /api/settings/spectral-rc/`
- `POST /api/settings/spectral-rc/recompute/` -- triggers manual recomputation
- `GET /api/settings/spectral-rc/diagnostics/` -- returns cluster diagnostics

### Review / admin / frontend

Add one settings card:

- enabled toggle
- cluster count slider
- spectral dimensions input
- anchor/query weight balance slider
- recompute interval selector
- "Recompute Now" button
- cluster size distribution chart
- eigenvalue spectrum chart (for advanced users)

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/spectral_rc.py` -- new service file
- `backend/apps/pipeline/tasks.py` -- add periodic clustering task
- `backend/apps/content/models.py` -- add `spectral_cluster_id` field
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-064 unit tests
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- `backend/apps/pipeline/services/clustering.py` -- FR-014 near-dup clustering
- `backend/apps/pipeline/services/ranker.py` -- no direct ranking change
- `backend/apps/suggestions/models.py` -- no per-suggestion fields
- `backend/apps/graph/models.py` -- read-only access to ExistingLink

## Test Plan

### 1. Relation matrix construction

- pages with anchor texts produce non-zero R1 rows
- pages with GSC queries produce non-zero R2 rows
- pages with neither produce zero rows (excluded from clustering)

### 2. Symmetrised adjacency

- A1(i,j) equals the number of shared anchor phrases between pages i and j
- A2(i,j) equals the number of shared queries between pages i and j
- both matrices are symmetric

### 3. Eigendecomposition

- top 16 eigenvectors are computed without error
- eigenvalues are in [0, 2] for normalised Laplacians
- small eigenvalues correspond to well-separated clusters

### 4. K-Means clustering

- K=32 clusters are assigned to all pages with relation data
- no cluster is excessively large (>50% of pages) or excessively small (<1 page)

### 5. Neutral fallback

- feature disabled -> all `spectral_cluster_id = null`
- insufficient data (no anchors AND no queries) -> state `insufficient_data`

### 6. Isolation

- clustering does not modify any page embedding or text content
- cluster labels do not change any existing suggestion score

### 7. Silhouette quality

- silhouette score is computed and stored
- score > 0.1 indicates meaningful cluster structure

### 8. Reproducibility

- same input data with same settings produces the same cluster assignments (K-Means seeded)

## Rollout Plan

### Step 1 -- compute and inspect

- run spectral clustering with defaults
- inspect cluster size distribution and silhouette score
- verify that pages in the same cluster share visible thematic relationships

### Step 2 -- silo analysis integration

- use spectral clusters alongside existing silo assignments
- identify cases where spectral clusters disagree with manual silos (potential misassignments)

### Step 3 -- link scope integration

- use spectral cluster membership as a soft constraint in link scoping
- prefer linking within the same spectral cluster (thematically coherent links)

## Risk List

- sparse relation matrices (few anchors or queries per page) may produce degenerate eigenvalues -- mitigated by requiring minimum data coverage before running;
- K=32 clusters may be too many or too few for some sites -- operator can adjust `num_clusters`;
- equal weighting of anchor and query relations may not be optimal -- operator can adjust `anchor_weight` / `query_weight`;
- eigendecomposition on very large sparse matrices (100K+ pages) may be slow -- mitigated by Lanczos method (sparse-friendly) and weekly-only recomputation;
- K-Means initialisation sensitivity -- mitigated by n_init=10 (10 random restarts).

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"spectral_rc.enabled": "true",
"spectral_rc.num_clusters": "32",
"spectral_rc.spectral_dims": "16",
"spectral_rc.anchor_weight": "0.5",
"spectral_rc.query_weight": "0.5",
"spectral_rc.recompute_interval_days": "7",
```

**Why these values:**

- `enabled = true` -- compute clusters from day one for silo analysis.
- `num_clusters = 32` -- good balance between granularity and interpretability.
- `spectral_dims = 16` -- captures the most important grouping structure without noise.
- `anchor_weight = 0.5`, `query_weight = 0.5` -- no prior reason to prefer one relation over the other.
- `recompute_interval_days = 7` -- weekly is sufficient since site structure changes slowly.

### Migration note

FR-064 must ship a new data migration that upserts these six keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
