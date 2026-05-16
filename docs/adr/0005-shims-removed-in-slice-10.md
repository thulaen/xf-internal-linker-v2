# ADR 0005 — Backward-compatibility shims are removed in slice 10

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0001, ADR 0002.

## Context

When a module moves into its `api.py` shape (slices 3-9), some imports at call sites will not be updated in the same commit. Two strategies are available:

1. **No shims — every call site updated in the same slice.** The slice that moves a module also rewrites every importer. The slice's diff is wide.
2. **Shims allowed — old paths kept temporarily.** The slice that moves a module leaves a one-line shim file at the old path that re-exports from the new path. Call sites can be updated lazily. The slice's diff is narrow.

Option 1 produces wider but cleaner slices. Option 2 produces narrower slices but leaves shim files around the repo that pretend the old paths still exist.

The user's stated preference (project memory) is **no rollback, no fallback** for migrations: "migrations are one-way; new path added, old path deleted, same PR." The same principle suggests option 1 for the cross-module migration.

But the module-move slices are unusually large. A typical move (`content.api` in slice 4) touches hundreds of call sites. Cramming the move and every call-site update into one slice would make code review hard. The middle ground is to allow shims **for one slice at a time**, then guarantee their removal in a final slice.

## Decision

1. **Shims are allowed during slice rollout.** When a slice moves a module to its `api.py` shape, a one-line shim file at the old path is permitted. The shim does nothing except re-export from the new path.
2. **Each shim is labelled.** Every shim file starts with the comment `# xf-shim: removed-in-slice-10 -- see ADR 0005`. The pre-commit hook (added in slice 2) refuses any shim missing this marker.
3. **Slice 10 deletes every shim.** Slice 10 is a focused removal slice. Its single check: zero files in the repo contain the `xf-shim:` marker, and `import-linter` runs with zero exceptions.
4. **No new shims may be added after slice 10.** Once slice 10 closes, the pre-commit hook flips from "shims allowed if labelled" to "no shims allowed."

## Consequences

**Positive:**

- Slices 3-9 stay narrow and reviewable.
- Every shim has a defined removal date (slice 10).
- The pre-commit hook makes the removal mechanical: grep the repo for `xf-shim:`, delete each match's file, verify `import-linter` passes.
- The labelled-shim discipline keeps the "migrations are one-way" principle (project memory) honoured at the end of the migration — not at every micro-step inside it.

**Negative:**

- The repo carries up to nine shim files temporarily (one per module that has moved).
- A reader who sees a shim during slices 3-9 might briefly think the old path is still supported. The label answers the confusion.

**Trade-offs accepted:**

- The "migrations are one-way" principle is followed at the slice-10 boundary, not at each intermediate move. The label and the hook gate make the temporary state visible and time-bounded.

## References

- ADR 0001 — modular-monolith style.
- ADR 0002 — `api.py` public surface.
- [`docs/MODULAR-MONOLITH.md`](../MODULAR-MONOLITH.md) § Slice ledger — slice 10's single check.
- Project memory: "No rollback / no fallback for migrations" — the principle this ADR honours at the end of the rollout.
