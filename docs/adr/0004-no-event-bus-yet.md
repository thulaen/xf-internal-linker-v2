# ADR 0004 — No event bus is introduced now

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0001.

## Context

A common addition to a modular-monolith style is an internal event bus or publish-subscribe layer: module A publishes an event ("post applied"), module B subscribes, and the two are decoupled at the call boundary. The argument for adding a bus is that direct calls between modules — even through `api.py` — create coupling between sender and receiver. A bus replaces the call with a typed event record on a queue.

Two arguments against adding a bus now:

1. **No measured coupling problem.** We have not measured a place in the codebase today where direct calls create real coupling pain. A bus solves a problem we do not yet have.
2. **A bus adds real cost.** Either a new infrastructure surface (Redis Streams, Postgres LISTEN/NOTIFY, Kafka, NATS) or a hand-rolled queue. Either choice requires reliability, retry, dead-letter, monitoring, schema versioning, and operator dashboards. These are all real engineering costs.

Celery already gives us a queue for long-running jobs. The Celery queue is a workflow engine, not an event bus. Using Celery for fan-out events would conflate two purposes and produce confusing monitoring.

## Decision

**Do not introduce an internal event bus or publish-subscribe layer in this round of refactoring.** Cross-module communication goes through direct calls into the target module's `api.py`. Long-running and background work continues to use Celery.

Revisit this decision when at least one of the following is true:

- A measured place in the codebase shows a call-chain through three or more modules that would be simpler as a published event.
- An external consumer (a future plugin, a future second service, a future analytics export) needs the same event that internal code already produces.
- A real-time fan-out is needed where one upstream change must reach N downstream modules in parallel.

## Consequences

**Positive:**

- Zero new infrastructure to operate this round.
- The `import-linter` boundary check works as-is; it does not have to model an "indirect call through the bus" case.
- Direct calls are simple to test (one mock, one assertion).

**Negative:**

- Modules are coupled at the call boundary. A change to `pipeline.api`'s signature ripples to its callers.
- A future bus addition is itself a future ADR and a future migration.

**Trade-offs accepted:**

- The direct-call coupling is real but small. Slice 2-9 will surface every call site through the `import-linter` baseline, so the cost of a signature change is bounded and visible.

## References

- ADR 0001 — modular-monolith style.
- Fowler — *Patterns of Enterprise Application Architecture*, on event-driven patterns and when not to use them.
- Hohpe & Woolf 2003 — *Enterprise Integration Patterns*, on the cost of a publish-subscribe layer.
- Celery documentation — workflow vs. event distinction: <https://docs.celeryq.dev/>.
