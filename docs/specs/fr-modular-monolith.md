# FR — Modular Monolith Architectural Style

[SPEC CITED: feature=fr-modular-monolith kind=academic_paper id=https://doi.org/10.1145/361598.361623 verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=academic_paper id=https://doi.org/10.1109/PROC.1980.11805 verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=academic_paper id=https://www.melconway.com/Home/Committees_Paper.html verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=patent id=https://patents.google.com/patent/US10700948B2 verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=patent id=https://patents.google.com/patent/US8645233B2 verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_literature id=https://www.iso.org/standard/74393.html verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_literature id=https://www.iso.org/standard/72089.html verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_literature id=https://www.oreilly.com/library/view/test-driven-development/0321146530/ verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://www.cosmicpython.com/book/preface.html verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://import-linter.readthedocs.io/ verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://nx.dev/concepts/decisions/project-dependency-rules verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://github.com/seddonym/grimp verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://www.milanjovanovic.tech/blog/what-is-a-modular-monolith verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_doc id=https://kraken-tech.medium.com/from-monolith-to-modular-monolith-at-kraken-bb56f7b65aca verified_at=2026-05-16]
[SPEC CITED: feature=fr-modular-monolith kind=technical_literature id=https://www.gopl.io/ verified_at=2026-05-16]
[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]

## Goal

State the rules every later slice references when refactoring the Django backend into a modular monolith. The rules are derived from cited sources, not from author preference.

## Sources of truth

| Source | Why it is used here |
|---|---|
| Parnas 1972 — *On the Criteria To Be Used in Decomposing Systems into Modules* | Establishes information hiding as the basis for module boundaries; provides the rule that "a module is a unit of change, not a folder." |
| Lehman 1980 — *Programs, Life Cycles, and Laws of Software Evolution* | Establishes that code without an architecture description drifts toward higher entropy; supports the requirement that the foundation document exists before any move. |
| Conway 1968 — *How Do Committees Invent?* | Establishes that module shape mirrors decision boundaries; supports the rule that the module map matches the user's mental model, not an arbitrary technical split. |
| US10700948B2 — architectural fitness functions | Patent on machine-checkable architecture rules; supports the slice-2 introduction of `import-linter` as the rule engine. |
| US8645233B2 — module-dependency enforcement | Patent on dependency-direction enforcement at build time; supports the dependency-direction rule. |
| ISO/IEC/IEEE 42010:2022 — architecture description | Requires a structured description naming concerns, stakeholders, viewpoints; the structure of [`docs/MODULAR-MONOLITH.md`](MODULAR-MONOLITH.md) follows this. |
| ISO/IEC/IEEE 29148:2018 — requirements engineering | Defines requirements engineering information items; the BDD shape of every slice's acceptance criteria follows this. |
| Beck 2002 — *Test-Driven Development: By Example* | Establishes the Red-Green-Refactor cycle this slice uses. |
| Percival & Gregory 2020 — *Architecture Patterns with Python* | Practitioner reference for explicit boundaries inside a single Python codebase. |
| Milan Jovanovic — *What Is a Modular Monolith?* | Practitioner writeup of the style with worked examples. |
| Kraken Technologies — *From monolith to modular monolith at Kraken* | Industry case study at a comparable scale. |
| import-linter | The slice-2 tool that enforces the boundary rule. |
| Nx enforce-module-boundaries | TypeScript-world equivalent; cited because the Angular frontend will benefit from the same rule in a later slice. |
| grimp | The graph library `import-linter` uses; cited so the dependency analysis is reproducible. |
| Nygard — *Documenting Architecture Decisions* | The ADR template every decision file uses. |

## Required rule

The modular-monolith style applies to the Django backend under `backend/`. Every later slice that moves code into the style does so under the same five conditions:

1. **One foundation document** ([`docs/MODULAR-MONOLITH.md`](MODULAR-MONOLITH.md)) names the nine modules, the services tier, the public-interface convention, the boundary rule, the dependency direction, the test plan, and the slice ledger.
2. **One `api.py` per module** is the public surface (ADR 0002).
3. **Cross-module Python imports go through `api.py` only** (ADR 0001).
4. **Cross-module Postgres foreign keys are allowed** (ADR 0003).
5. **No event bus is introduced in this round** (ADR 0004). Shims are allowed during rollout and removed in slice 10 (ADR 0005).
6. **Go services live in a services tier** as peer modules to the nine Django modules (ADR 0006). Each Go service exposes a `services/<name>/api.proto` (gRPC) or `services/<name>/api.http.md` (HTTP+JSON) contract; Python and Go never import each other directly; the cross-language boundary is RPC.

Every code-changing slice carries the standard handoff markers:

`[SPEC PROOF: specs=docs/specs/fr-modular-monolith.md source_types=academic_paper,patent,technical_literature,technical_doc checked_at=<YYYY-MM-DD> status=<current|updated>]`
`[BDD PROOF: Given <state> When <action> Then <outcome>]`
`[TDD PROOF: before_or_alongside=yes tests=<commands> result=passed]`
`[SPEC CODE REVIEW: specs=docs/specs/fr-modular-monolith.md result=<matched|updated>]`

## Acceptance criteria (BDD)

```gherkin
Feature: Slice 1 — Foundation

  Scenario: The foundation document lands
    Given the project had no shared definition of a module
    When slice 1 closes
    Then docs/MODULAR-MONOLITH.md exists with the seven required sections
    And the nine module stubs exist under docs/modules/
    And the five ADRs exist under docs/adr/ with Context / Decision / Consequences
    And this spec carries SPEC FRESHNESS in the current calendar month
    And each of the cited sources has at least one SPEC CITED line above
    And PLAIN-ENGLISH-RULE.md includes the new glossary terms used by the rule
    And AGENTS.md, CLAUDE.md, CODEX.md, GEMINI.md each carry the ABSOLUTE — Modular Monolith rule
    And AI-CONTEXT.md Session Gate has a Modular Monolith subsection
    And docs/v2-master-plan.md § 3 links to docs/MODULAR-MONOLITH.md

  Scenario: A future slice references this spec
    Given a later slice is about to move a module into its api.py shape
    When the agent reads docs/MODULAR-MONOLITH.md and this spec
    Then the agent finds the boundary rule, the dependency direction, and the slice ledger
    And the agent knows which check to run for the slice

  Scenario: Existing Go service is captured by the architecture
    Given services/streamd existed before this refactor
    When slice 1 is complete
    Then docs/MODULAR-MONOLITH.md lists services/streamd in the services tier
    And docs/modules/services.md exists with streamd as a member
    And docs/adr/0006-go-services-tier.md records the decision
    And the strict rule in AGENTS.md / CLAUDE.md / CODEX.md / GEMINI.md mentions the services tier
```

## Services tier

The services tier is the dedicated home for Go sidecar programs that run alongside the Django app. [ADR 0006](../adr/0006-go-services-tier.md) is the decision of record.

Today the tier contains one member: `services/streamd` (the stream-engine broker). Future members arrive only after the native-rewrite escalation proves Python cannot meet the target, per [ADR 0006](../adr/0006-go-services-tier.md) § Decision.

The cross-language boundary is RPC. Python never imports Go and Go never embeds Python. The slice-1.5 hook `.githooks/check-no-cross-language-import.py` enforces this at commit time; the sibling slice-1.5 hook `.githooks/check-go-service-contract.py` enforces the contract + binary presence shape. Quality tooling (`scripts/run-go-quality.sh` + nine per-stage sub-scripts) lands in the same slice. The streamd binary promotion (`services/streamd/cmd/streamd/main.go` + `services/streamd/api.proto`) lands in slice 1.5 as the reference shape every future Go service follows.

The services tier does not change the nine-module dependency direction. Go services are sidecars, not a layer.

## Test plan

Slice 1 verification:

- `python -m pytest -p randomly -q .githooks/test_check_modular_monolith_docs.py` passes (7 tests).
- `python -m pytest -p randomly -q .githooks/test_check_spec_citation.py` still passes (regression).
- `python -m coverage run --data-file C:/tmp/.cov-slice1 -m pytest .githooks/test_check_modular_monolith_docs.py` then `python -m coverage report --data-file C:/tmp/.cov-slice1 --include=".githooks/test_check_modular_monolith_docs.py" --fail-under=95` succeeds.

Slice 1.5 verification (when slice 1.5 lands): `bash scripts/run-go-quality.sh` runs the nine Go quality stages against `services/streamd` and exits 0. `.githooks/check-no-cross-language-import.py` and `.githooks/check-go-service-contract.py` are wired into `scripts/precommit-docker.sh` as hard-block gates. `services/streamd/cmd/streamd/main.go` builds, runs, and answers Publish / Subscribe / Manage / Health RPCs over the `streamd_sock` Unix socket. The speed benchmark either confirms p99 < 1 ms / throughput > 50,000 msg/s or files a `[PERFORMANCE EXEMPTION: ...]` marker with measured numbers.

Slice 2 verification (when slice 2 lands): `import-linter` runs from the pre-commit hook and reports its baseline ratchet.

Slices 3-9 verification: each slice's own `import-linter` ratchet drops by the count of cross-module reaches into the slice's module.

Slice 10 verification: `import-linter` runs with zero violations and zero exceptions; the repo carries zero files with the `xf-shim:` marker.

## Monthly review

This spec must be reviewed and `[SPEC FRESHNESS]` updated on or before `next_review`. The review checks:

1. The nine module names still match the codebase's reality.
2. The cited sources remain accessible (DOIs resolve, URLs return 200).
3. The slice ledger reflects the current slice progress.
4. Any new ADR is linked from the References section below.

## Commit behaviour

`.githooks/check-spec-citation.py` reads this spec when a code-changing commit names it in `[SPEC PROOF]`. The hook checks `[SPEC FRESHNESS]` is in the current month and the cited sources line up.

## References

- [`docs/MODULAR-MONOLITH.md`](MODULAR-MONOLITH.md) — canonical architecture document.
- [`docs/adr/0001-modular-monolith.md`](../adr/0001-modular-monolith.md) — overall decision.
- [`docs/adr/0002-public-interface-api-py.md`](../adr/0002-public-interface-api-py.md) — `api.py` convention.
- [`docs/adr/0003-cross-module-fk-allowed.md`](../adr/0003-cross-module-fk-allowed.md) — FK / Python-import boundary split.
- [`docs/adr/0004-no-event-bus-yet.md`](../adr/0004-no-event-bus-yet.md) — no event bus yet.
- [`docs/adr/0005-shims-removed-in-slice-10.md`](../adr/0005-shims-removed-in-slice-10.md) — shim removal in slice 10.
- [`docs/adr/0006-go-services-tier.md`](../adr/0006-go-services-tier.md) — Go services tier as a peer module type.
- [`docs/modules/services.md`](../modules/services.md) — services-tier module documentation.

## Citations

- Parnas 1972 — *On the Criteria To Be Used in Decomposing Systems into Modules.* Communications of the ACM 15(12). DOI 10.1145/361598.361623.
- Lehman 1980 — *Programs, Life Cycles, and Laws of Software Evolution.* Proceedings of the IEEE 68(9). DOI 10.1109/PROC.1980.11805.
- Conway 1968 — *How Do Committees Invent?* Datamation. URL melconway.com/Home/Committees_Paper.html.
- US Patent US10700948B2 — *Architectural fitness functions and verification.*
- US Patent US8645233B2 — *Module dependency enforcement at build time.*
- ISO/IEC/IEEE 42010:2022 — *Software, systems and enterprise — Architecture description.*
- ISO/IEC/IEEE 29148:2018 — *Systems and software engineering — Requirements engineering.*
- Beck 2002 — *Test-Driven Development: By Example.* Addison-Wesley.
- Percival & Gregory 2020 — *Architecture Patterns with Python.* O'Reilly. URL cosmicpython.com.
- Milan Jovanovic — *What Is a Modular Monolith?* URL milanjovanovic.tech/blog/what-is-a-modular-monolith.
- Kraken Technologies — *From monolith to modular monolith at Kraken.* URL kraken-tech.medium.com.
- import-linter docs — URL import-linter.readthedocs.io.
- Nx enforce-module-boundaries — URL nx.dev/concepts/decisions/project-dependency-rules.
- grimp — URL github.com/seddonym/grimp.
- Nygard — *Documenting Architecture Decisions.* URL cognitect.com/blog/2011/11/15/documenting-architecture-decisions.
- Donovan & Kernighan 2015 — *The Go Programming Language.* Addison-Wesley. URL gopl.io. Establishes the goroutine + `net/http` concurrency model that justifies Go's fit for the services tier (ADR 0006).
