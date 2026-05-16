# Module: suggestions

**Layer:** 2 (business).
**Status:** Stub — full detail lands in slice 7.
**Maps to today:** suggestion-status state machine, review queue, anchor policy enforcement, near-duplicate clustering, audit-trail glue for human reviewers.

## Plain-English summary

The suggestions module owns proposed links. It takes the ranked candidates `pipeline` produces, runs anchor-policy checks, clusters near-duplicates, and exposes them to the human reviewer. It owns the state machine: a suggestion is `proposed`, then `reviewed`, then `applied` or `rejected`. It owns the audit trail of who reviewed what.

If a function is about a human reviewer seeing or acting on a suggestion, it belongs here.

## Public interface

`suggestions.api` exports the review-side call surface. Examples slated for slice 7:

- `Suggestion`, `SuggestionStatus`
- `propose(ranked: RankedCandidate) -> Suggestion`
- `mark_reviewed(suggestion_id: int, reviewer: str)`
- `mark_applied(suggestion_id: int, applied_at: datetime)`
- `mark_rejected(suggestion_id: int, reason: str)`
- `cluster_near_duplicates(suggestions: list[Suggestion]) -> list[Cluster]`
- `enforce_anchor_policy(suggestion: Suggestion) -> AnchorPolicyResult`

State transitions are private inside the module. The public surface only exposes the verbs.

## Job (the "and"-test)

Suggestions owns one job: **manage proposed links and the human review of them.** It does not own ranking (pipeline) or graph storage (graph) or analytics ingestion (analytics).

## Owned tables

- `Suggestion`, `SuggestionStatus` (current row), `SuggestionHistory` (append-only audit)
- `NearDuplicateCluster` and the per-cluster supersede tracking (per the no-duplicates rule)
- `AnchorPolicyResult`

The full list arrives with the slice-7 move.

## Dependencies

- `platform` (audit logging, feature flags, plain-English helpers)
- `content` (read posts and anchor phrases to render the review surface)
- `pipeline` (consume ranked candidates as input)

Suggestions does **not** depend on `analytics`, `graph`, `operations`, `governance` directly.

## Open questions

- Where does the FR-014 near-duplicate clustering UI live — in `suggestions` (close to the data) or in `operations` (close to the dashboards)? Current lean: backend services in `suggestions`, frontend cards in the Angular bundle which talks to `suggestions.api`.
- The "proposed but not yet applied" tag is a glossary term — confirm the model field name matches the glossary entry exactly.

## Citations

- Cucumber Gherkin reference — BDD state-transition specification used to document the suggestion state machine.
- Beck 2002 — TDD for the state-machine tests.

## Slice that moves this module

Slice 7. Lands after `pipeline` because `pipeline.api` is its main input.
