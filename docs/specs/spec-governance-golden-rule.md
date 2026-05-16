# Source-Backed Spec Governance Golden Rule

[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.iso.org/standard/74393.html verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.iso.org/standard/72089.html verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://cucumber.io/docs/gherkin/reference/ verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.oreilly.com/library/view/test-driven-development/0321146530/ verified_at=2026-05-16]
[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]

## Goal

Every code change must start from a current written spec. The spec may be a
software design document, product requirements document, or focused technical
spec. The spec must cite at least one source of truth from patents, academic
papers, formal standards, official technical docs, or respected technical
literature.

## Sources Of Truth

| Source | Why it is used here |
|---|---|
| ISO/IEC/IEEE 42010:2022 architecture description standard | Requires a structured architecture description for software and systems. |
| ISO/IEC/IEEE 29148:2018 requirements engineering standard | Defines requirements engineering and requirements information items. |
| Cucumber Gherkin reference | Defines `Given`, `When`, and `Then` behavior wording used by behavior plans. |
| Kent Beck, *Test-Driven Development: By Example* | Establishes the test-first practice used for code changes. |

## Required Rule

Before coding, agents must confirm a related spec exists and was reviewed in
the current calendar month. If the spec is missing, stale, or lacks source
citations, the commit must fail.

Every production source commit must include these staged handoff markers:

`[SPEC PROOF: specs=<paths> source_types=<patent|academic_paper|technical_literature|technical_doc> checked_at=<YYYY-MM-DD> status=<current|updated>]`

`[BDD PROOF: Given <state> When <action> Then <outcome>]`

`[TDD PROOF: before_or_alongside=yes tests=<commands> result=passed]`

`[SPEC CODE REVIEW: specs=<paths> result=<matched|updated>]`

## Monthly Review

Each spec must include:

`[SPEC FRESHNESS: reviewed_at=<YYYY-MM-DD> next_review=<YYYY-MM-DD>]`

The `reviewed_at` date must be in the current calendar month. The
`next_review` date must be today or later. This keeps source-backed specs
current while still allowing focused code changes.

## Commit Behavior

The commit hook checks only files in the staged commit and the spec files named
by the handoff marker. It does not scan unrelated specs by default. A full
manual audit can still scan all specs when needed.
