# ADR 0001 — Adopt a modular-monolith style for the Django backend

**Date:** 2026-05-16
**Status:** Accepted
**Deciders:** Project owner.
**Supersedes:** None.

## Context

The Django backend has grown to roughly two-dozen `apps/<name>/` packages. Imports cross app boundaries in many directions. Reading code requires holding many implicit conventions in mind. Su (2024) and Lehman (1980) both show that codebases without a shared definition of "module" drift toward higher entropy, and changes ripple unpredictably.

Three styles were considered:

1. **Stay as-is** — accept the implicit conventions, document them retroactively.
2. **Adopt a modular-monolith style** — group `apps/<name>/` into nine named modules, give each module a single public-interface file, enforce a one-way dependency direction.
3. **Split into microservices** — separate the backend into independently deployable services.

The microservice split would cost roughly 10× what the modular split costs, would introduce a network boundary between code paths that today are a single function call, and would solve a problem (multi-team scale, polyglot runtime, independent deploy) that we don't have. The team is one person assisted by AI agents.

Staying as-is leaves the cost of every future change in code review. The modular-monolith style adds enforceable contracts (`import-linter`, hook checks) for a one-time cost and a small recurring cost per slice.

## Decision

Adopt a **modular-monolith** architectural style for the Django backend. Concretely:

1. Group `backend/apps/<name>/` into nine modules: `platform`, `content`, `sources`, `pipeline`, `suggestions`, `analytics`, `graph`, `operations`, `governance`.
2. Each module declares its public surface in one file: `api.py`.
3. Cross-module imports go through `api.py` only. Reaching into private files is forbidden.
4. Imports flow in one direction, from higher layers to lower (foundation → business → orchestration).
5. The runtime stays as one deployable unit: one Django container, one set of Celery workers, one database. No microservice split.
6. The four design choices that fall out of (1)-(5) are recorded in ADRs 0002 through 0005.

The rollout happens across slices 1-10. Slice 1 produces the foundation documents. Slices 2-9 move one module at a time. Slice 10 deletes the shims.

## Consequences

**Positive:**

- Every reader can answer "where does this responsibility live?" by reading [`docs/MODULAR-MONOLITH.md`](../MODULAR-MONOLITH.md).
- The pre-commit hook (slice 2) prevents new cross-module import violations from landing.
- Cross-module changes become rarer; when they happen, they touch one `api.py` per side.
- The modules are an editorial layer only; the runtime is unchanged. There is no extra latency, no extra failure mode, no extra deploy.

**Negative:**

- Slices 2-9 introduce churn. Each slice moves one module's call sites and may produce a shim file.
- The `api.py` convention is enforced by tools that need maintenance (`import-linter`, hook scripts).
- Until slice 10 finishes, some shims exist as backward-compatibility files. ADR 0005 records the planned removal.

**Trade-offs accepted:**

- The dependency direction is strict and may force a "typed record on `api.py`" pattern in places where a direct call would have been quicker. The cost is intentional — explicit typed records are easier to test and easier to change later than a free-form call across modules.
- No event bus or pub-sub is introduced (see ADR 0004). If a future use case proves a bus is needed, it can be added without revisiting this decision.

## References

- Parnas 1972 — *On the Criteria To Be Used in Decomposing Systems into Modules.*
- Lehman 1980 — *Programs, Life Cycles, and Laws of Software Evolution.*
- Conway 1968 — *How Do Committees Invent?*
- Su 2024 — modular-monolith industry survey.
- US10700948B2 — architectural fitness functions.
- US8645233B2 — module-dependency enforcement.
- ISO/IEC/IEEE 42010:2022 — architecture description.
- Percival & Gregory 2020 — *Architecture Patterns with Python.*
- Nygard — *Documenting Architecture Decisions* (ADR template).
- [`docs/MODULAR-MONOLITH.md`](../MODULAR-MONOLITH.md) — the canonical architecture document.
- [`docs/specs/fr-modular-monolith.md`](../specs/fr-modular-monolith.md) — the source-backed spec.
