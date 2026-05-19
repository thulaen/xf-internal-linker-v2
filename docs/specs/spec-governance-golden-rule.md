# Source-Backed Spec Governance Golden Rule

[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.iso.org/standard/74393.html verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.iso.org/standard/72089.html verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://cucumber.io/docs/gherkin/reference/ verified_at=2026-05-16]
[SPEC CITED: feature=spec-governance-golden-rule kind=technical_literature id=https://www.oreilly.com/library/view/test-driven-development/0321146530/ verified_at=2026-05-16]
[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]

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

Before coding, agents must also state the exact scope they are about to touch,
the specification they read, whether that specification fully covers the
intended change, and whether any gap was filled with authoritative research.
If the related spec is absent, ambiguous, or silent on an important decision,
the agent must stop until the spec is updated with source-backed requirements.

Every production source commit must include these staged handoff markers:

`[SPEC PROOF: specs=<paths> source_types=<patent|academic_paper|technical_literature|technical_doc> checked_at=<YYYY-MM-DD> status=<current|updated>]`

`[SPEC RESEARCH GATE: scope=<plain-path-or-feature> specs=<paths> coverage=<full|updated> gaps=<none|filled> research=<none|citation-ids>]`

`[BDD PROOF: Given <state> When <action> Then <outcome>]`

`[TDD PROOF: before_or_alongside=yes tests=<commands> result=passed]`

`[SPEC CODE REVIEW: specs=<paths> result=<matched|updated>]`

## Monthly Review

Each spec must include:

`[SPEC FRESHNESS: reviewed_at=<YYYY-MM-DD> next_review=<YYYY-MM-DD>]`

The `reviewed_at` date must be in the current calendar month. The
`next_review` date must be today or later. This keeps source-backed specs
current while still allowing focused code changes.

## Research Gap Handling

The `coverage` field is `full` when the existing spec already states the
needed behavior. It is `updated` when the agent had to update the spec before
code. The `gaps` field is `none` when no missing requirement was found. It is
`filled` when the agent used research to close a gap in the spec.

When `coverage=updated` or `gaps=filled`, the `research` field must name at
least one source identifier. The source must support the overall feature,
module, system architecture, architecture boundary, data model, background job,
public interface, or test policy being changed. For ranking work, the source
must support the ranking weight, ranking method, ranking algorithm, or full
ranking pipeline being changed. For frontend work, the source must support the
user-facing design, interaction pattern, accessibility requirement, or interface
system being changed. For security, code-review, or error-tracking work, the
source must support the security model, review policy, incident workflow,
observability policy, or error-tracking integration being changed. For
scalability work, the source must support the capacity model, load behavior,
growth policy, queueing strategy, performance budget, or full scaling plan
being changed. For regression-risk work, the source must support the
compatibility policy, rollback strategy, test-risk model, failure-prevention
policy, or release-safety plan being changed. It must not be a citation for a
tiny local code edit such as a helper function, line format, CSS selector, or
one-off implementation detail.
Accepted sources are the same source types used by `[SPEC CITED:]`: patents,
academic papers, formal standards, official technical docs, or respected
technical literature.

## Commit Behavior

The commit hook checks only files in the staged commit and the spec files named
by the handoff markers. It does not scan unrelated specs by default. A full
manual audit can still scan all specs when needed. For code changes, the hook
also requires `[SPEC RESEARCH GATE:]` to name every spec listed in
`[SPEC PROOF:]`.
