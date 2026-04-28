# Group A.3 - Random Walk Path Deduplication

## Overview
**Goal:** Optimize the storage of random walk results (e.g., from the Pixie candidate generation walker) by persisting deduplicated visit counts rather than raw sequence paths. 
**Impact:** Cuts database disk usage by an order of magnitude on dense graphs while changing absolutely nothing about candidate ranking or multi-hit score boosting.

## Research & Rank Equivalence
- **Page-Brin 1998 (PageRank):** The original formulation demonstrates that the authoritative importance of a node is determined by its visitation probability in the limit of a random walk. The explicit sequence of hops is immaterial to the final vector; only the aggregate visitation frequency matters.
- **Bahmani, Chowdhury, Goel (2010) - Fast Incremental PageRank:** Proves that incremental random walk methods and their derivatives (like personalized subset walks) can achieve exact rank equivalence by solely accumulating visitation counts per destination node.

In the context of the Pixie candidate generation walk (FR-021), the ranking is derived via the number of times a `visited_node` is reached from a `start_entity`, along with non-linear multi-hit boosting (e.g., `sqrt(visit_count)`). Because the scoring function only depends on `visit_count` and the number of distinct query entities that reached the candidate, the literal ordered sequence of the walk is discarded during scoring anyway.

## Storage Optimization
**Old Model (Hypothetical non-deduped):**
If a walker takes 5,000 steps and hits the same highly connected article 400 times, storing raw paths would require 5,000 rows.

**New Model (Deduplicated):**
We store exactly one row per `(start_entity, visited_node)` tuple.
- `PixieWalkVisit` model:
  - `source_content`: ForeignKey to `ContentItem`
  - `visited_content`: ForeignKey to `ContentItem`
  - `visit_count`: IntegerField
  - `signal_version`: CharField (e.g., the current graph generation version)

For a walk of 5,000 steps covering 150 unique destination articles, we store exactly 150 rows. 

## Persistence Strategy
As decided during the implementation phase:
1. **Strict Overwrite Policy:** To prevent version bloat, when a new pipeline run generates candidates for a given `source_content`, the system uses an upsert/overwrite strategy. Previous `PixieWalkVisit` records for that source are deleted or cleanly overwritten.
2. **Fresh Walks:** Despite the strict overwrite policy, random walks are executed *fresh* for all processed content on each run. This ensures that old content can instantly discover newly added nodes in the graph without relying on stale serialized walk state.
