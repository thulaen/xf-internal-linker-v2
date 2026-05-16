# ADR 0003 — Cross-module Postgres foreign keys are allowed; cross-module Python imports are not

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Related:** ADR 0001, ADR 0002.

## Context

In a strict modular-monolith style, the question of database boundaries arises. Three positions are common:

1. **One database per module.** Every module owns its tables and reaches out only via API calls. The cleanest split, but moves us toward microservices in everything but deploy.
2. **Shared database, no cross-module foreign keys.** Tables live in one Postgres database, but a row in module A's table is referenced from module B's table by an integer ID with no FK constraint enforced at the DB layer. Avoids cascade surprises but loses Postgres' guarantees.
3. **Shared database, cross-module FKs allowed.** Tables live in one Postgres database. A row in module B's table that points at module A's table uses a real `models.ForeignKey(...)`. The database enforces referential integrity.

Position 1 throws away the runtime benefits the modular monolith was supposed to keep. Position 2 trades real database guarantees for an architectural rule that only sounds clean. Postgres handles FK enforcement cheaply, and losing cascade-on-delete or `ON DELETE RESTRICT` introduces data-corruption risk.

Position 3 keeps Postgres doing what Postgres does well. The modular-monolith rule is about **Python imports**, not about the database. A foreign key declared in module B's `models.py` that points at module A's table is allowed; what is not allowed is module B's Python code reaching into module A's private files to call functions or read attributes.

## Decision

1. **Cross-module Postgres foreign keys are allowed.** A `models.ForeignKey(...)` in module B's `models.py` may point at a table owned by module A. The `on_delete=` policy must be declared (already enforced by `.githooks/check-fk-on-delete.py`).
2. **Cross-module Python imports remain forbidden** unless they go through the target module's `api.py`. Module B's Python code may not `from apps.a._internal import foo`.
3. **The typed record on `api.py` is the canonical Python boundary.** If module B needs to read or filter rows owned by module A, the verb lives on `apps.a.api`. Examples: `get_post(id)`, `iter_recent_posts(since)`.
4. **Migrations may cross module boundaries.** A migration in module B may reference a table owned by module A. The migration is a database-layer operation, not a Python-layer one.

## Consequences

**Positive:**

- Postgres continues to enforce referential integrity. Orphaned rows, cascade-on-delete, and `ON DELETE RESTRICT` keep working.
- The Python boundary stays clean and machine-checkable by `import-linter`.
- No new database surface area is required; the existing FK relationships continue to work.

**Negative:**

- The "Python boundary" and "database boundary" are not the same line. A reader must remember that the rule applies to Python imports, not to schema relationships.
- A future move to a one-database-per-module pattern (if microservices ever appear) would require breaking some FK constraints. This is a future-cost, not a current-cost.

**Trade-offs accepted:**

- The mixed boundary is documented (in this ADR and in [`docs/MODULAR-MONOLITH.md`](../MODULAR-MONOLITH.md)) rather than enforced by a single rule. A reader who confuses the two boundaries reads the wrong rule; the rule itself stays simple.

## References

- ADR 0001 — modular-monolith style.
- ADR 0002 — `api.py` as the public Python surface.
- Percival & Gregory 2020 — *Architecture Patterns with Python*, on the database/Python boundary in monoliths.
- PostgreSQL documentation — referential integrity, `ON DELETE` clauses: <https://www.postgresql.org/docs/current/ddl-constraints.html>.
- `.githooks/check-fk-on-delete.py` — existing check that every FK declares `on_delete=`.
