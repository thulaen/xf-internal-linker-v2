# AA.5 - Operations Feed

## Requirement

Operator-visible state changes must emit one plain-English Operations Feed event through `apps.ops_feed.services.emit(...)`.

Events deduplicate for 60 seconds by event type, source, related entity type, and related entity id. The latest wording updates the existing row, and the occurrence counter increments.

## Covered Areas

Content imports, NLP loading, embedding model state, ranking math, crawler progress, job completion, master pause changes, meta-algorithm runs or toggles, and suggestion-readiness transitions should appear in the feed when they matter to an operator.
