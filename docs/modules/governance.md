# Module: governance

**Layer:** 3 (orchestration).
**Status:** Stub — full detail lands in slice 9.
**Maps to today:** `docs/specs/`, `docs/adr/`, `PLAIN-ENGLISH-RULE.md`, the citation cache, the `.githooks/` enforcement layer, the business-logic checklist runner, the paper-trail policy.

## Plain-English summary

The governance module owns the rules. Specs, Architecture Decision Records, the plain-English glossary, the citation cache, the pre-commit hook enforcement glue, the business-logic checklist runner, the paper-trail policy. If a function asks "is this commit allowed?" or "where does this rule live?", it belongs here.

Operations and governance are siblings at Layer 3. Operations runs the system. Governance keeps the rules consistent.

## Public interface

`governance.api` exports the rule-side verbs and the queries hooks use. Examples slated for slice 9:

- `Citation`, `CitationCache`
- `lookup_citation(key: str) -> Citation | None`
- `register_citation(key: str, kind: str, id: str, verified_at: date)`
- `current_spec_freshness(spec_path: str) -> SpecFreshness`
- `enforce_business_logic_checklist(area: str) -> list[ChecklistFinding]`
- `paper_trail_policy_check(entry: PaperTrailEntry) -> PolicyResult`

The hook scripts under `.githooks/` are private to the repo's enforcement layer; they call `governance.api` for the data they need.

## Job (the "and"-test)

Governance owns one job: **keep the project's rules consistent and machine-checkable.** It does not own running jobs (`operations`) or any business decision.

## Owned tables

- `CitationCache` (already exists in `apps/citations/`)
- `SpecFreshness`
- `BusinessLogicChecklistRun`
- `PaperTrailPolicy`

The full list arrives with the slice-9 move.

## Dependencies

- `platform` (audit logging, plain-English helpers)
- `operations` (read AutoIssue and paper-trail rows for cross-checks)

Governance may import from Layer 1 and from `operations` at Layer 3. No module imports from `governance`.

## Open questions

- The plain-English glossary lives in `PLAIN-ENGLISH-RULE.md` (a top-level file). Slice 9 confirms that the file stays at the repo root and the `governance` module reads it, rather than the file moving inside `apps/governance/`.
- The `manage.py` commands that operate on the AutoIssue table read shared schemas — confirm the schema definitions live in `operations.api` and the rule-checks call them from `governance`.

## Citations

- ISO/IEC/IEEE 42010:2022 — architecture-description governance.
- ISO/IEC/IEEE 29148:2018 — requirements-engineering governance.
- Nygard — *Documenting Architecture Decisions* (the ADR pattern the module enforces).

## Slice that moves this module

Slice 9 (with `operations`).
