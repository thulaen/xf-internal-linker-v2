# AA.6 - Suggestion Readiness Gate

## Requirement

The Review page must not show suggestions until the backend says the suggestion system is ready.

The frontend calls `GET /api/suggestions/readiness/` and subscribes to the `suggestions.readiness` realtime topic. When a broadcast arrives, it refreshes the readiness payload and updates the visible prerequisite list.

## Operator Copy

When blocked, the overlay headline is `Preparing Suggestions...` and the list explains which prerequisites are still pending in plain English.
