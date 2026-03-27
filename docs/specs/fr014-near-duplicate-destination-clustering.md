# FR-014 - Near-Duplicate Destination Clustering

## Confirmation

Simple version first.

- Active target confirmed: `Phase 17 / FR-014 - Near-Duplicate Destination Clustering` is the next queued roadmap item in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Doc gap confirmed: this spec file was missing.
- Repo confirmed: the live branch already has separate ranking layers for semantic, keyword, authority, freshness, matching, corroboration, propagation, field-aware relevance, and click-distance.

## Current Repo Map

### Items available for clustering
- `backend/apps/content/models.py`
  - `ContentItem.embedding`: 1024-dim semantic vector (BAAI/bge-m3).
  - `ContentItem.content_hash`: Hash of raw body (exact duplicate detection).
  - `ContentItem.title`: Text name.
  - `ContentItem.url`: Unique identifier.
- `backend/apps/pipeline/services/ranker.py`
  - `ScoredCandidate`: Dataclass carrying suggestion-time scores.

### Items not available
- No formal `Cluster` or `Canonical` model relationship.
- No background task to group near-duplicates.
- No UI to manage clusters or "merge" redundant pages.

## Plain-English Summary

Simple version first.

Sometimes multiple pages on a site are nearly the same.
Example:
- A forum thread.
- The same thread in a "print-view" or "archive" format.
- A resource that also has a dedicated discussion thread.

FR-014 groups these "near-duplicates" into a **Cluster**.
One item in the cluster is chosen as the **Canonical** (the best version).

When the AI looks for links:
- It prefers the Canonical page.
- It suppresses (hides or penalizes) the other pages in that cluster.
- This prevents suggesting 5 links to the same thing.

## Problem Summary

Right now the ranker treats every URL as a unique, independent destination.
If a site has redundant content, the pipeline might generate multiple suggestions that are logically identical to the user, cluttering the review UI and the final page.

FR-014 adds a "Deduplication and Canonicalization" layer to ensure variety and quality.

## Goal

Add a `ContentCluster` model and a background `ClusteringService` that:
- groups items based on semantic similarity (embeddings);
- picks a primary representative (Canonical) based on authority/quality;
- allows manual overrides to fix errors;
- integrates into the ranking pipeline to suppress "subordinate" cluster members.

## Non-Goals

FR-014 does not:
- merge database records (items remain distinct);
- perform cross-source ID merging (per the constraint: "Do not default to cross-source canonicalization");
- delete redundant content from the source forum;
- implement final slate diversity (FR-015), which handles host-side link variety.

## Source Summary

Primary source:
- `US7698317B2` - Method and system for clustering and presenting search results.

Key insights:
- use transitive similarity (A similar to B, B similar to C) but with high confidence requirements;
- present only the representative (canonical) member to the user;
- allow users to expand clusters if they want to see "similar results" (not needed for our auto-linking, but helpful for review).

## Hard Scope Boundary

FR-014 must stay separate from:
- **FR-012 (Click Distance)**: Click distance is a structural prior; clustering is a content grouping.
- **FR-013 (Feedback-Driven)**: Feedback learns from pair success; clustering learns from content redundancy.
- **FR-015 (Final Slate Diversity)**: FR-015 prevents linking to the *same* destination too many times from one host. FR-014 prevents linking to *redundant versions* of a destination.

## Proposed Model

### `ContentCluster`
- `cluster_id` (UUID)
- `canonical_item` (FK to `ContentItem`, nullable)
- `is_manually_fixed` (Boolean) - prevent auto-updates if a human intervened.

### `ContentItem` Additions
- `cluster` (FK to `ContentCluster`, nullable)
- `is_canonical` (Boolean) - helper flag for the ranker.

## Clustering Logic

### Detection
Use `pgvector` distance on the `embedding` column.
- **Threshold**: Similarity > 0.96 (Distance < 0.04).
- **Secondary check**: If similarity is high but titles are vastly different, proceed with caution.

### Representative Selection
If cluster members are auto-detected, pick the canonical by:
1. `march_2026_pagerank` (Higher is better).
2. `velocity_score` (More recent/active is better).
3. `content_type` priority (e.g. `resource` > `thread`).

## Pipeline Suppression

When multiple candidates are found:
- If `candidate.is_canonical` is True, it keeps its full score.
- If `candidate.is_canonical` is False, apply a **Soft Suppression Factor** (default -50% to final score).
- This ensures the canonical usually wins, but if a subordinate is a *vastly* better match for a specific sentence, it can still surface (though usually, we just want the canonical).

## Operator Settings
- `clustering_enabled` (Bool)
- `similarity_threshold` (Float, 0.90..0.99)
- `suppression_penalty` (Float, 0.0..1.0)

## API Surface
- `GET /api/settings/clustering/`
- `PUT /api/settings/clustering/`
- `POST /api/settings/clustering/run/` - Trigger background pass.

## Implementation Workflow

1. **Models**: Add `ContentCluster` and migrate `ContentItem`.
2. **Service**: Implement `ClusteringService` using transitive grouping.
3. **Pipeline**: Update `ranker.py` and `pipeline.py` to identify cluster membership.
4. **UI**: Add cluster badges to the Review screen and a "Canonical" toggle.

## Final Rule

Simple version first.

Don't link to the same thing twice under different names.
If two pages are basically twins, pick the prettier twin and link to that.
If the AI gets it wrong, let the human fix the relationship.
