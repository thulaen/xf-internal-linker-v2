# Paper Trail Handoff Migration

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

`manage.py migrate_handoff_deferrals` turns unresolved-work prose in
`AGENT-HANDOFF.md` into searchable Paper Trail rows. This keeps deferred work in
the database-backed work queue instead of leaving it only in plain text.

## Behavior

Given a handoff entry contains a section headed `What has issues or errors`,
`What still has issues or errors`, or `What was deferred`, when the migration
command scans that entry, then it treats the section as deferred work.

Given that section has numbered or bulleted items, when the command scans the
section, then it creates one candidate Paper Trail row per item and keeps the
existing dedupe check before writing.

Given that section is a plain paragraph without bullets, when the command scans
the section, then it creates one candidate row from that paragraph if the text
is long enough to be useful.

Given the command is run more than once, when the same candidate appears again,
then the dedupe index prevents duplicate active Paper Trail rows.

## Scope

This spec covers only the legacy handoff migration command. It does not change
the Paper Trail row schema, the 10-per-session quota, the required source-backed
evidence fields, or the resolution command.

## Test Plan

- Add a database-backed command test proving `What still has issues or errors`
  is migrated.
- Keep the existing tests for `What has issues or errors`, dry-run behavior,
  category inference, linked AutoIssue extraction, citations, and dedupe.

## Citations

- [SPEC CITED: academic_paper] Parnas 1972 Communications of the ACM, "On the
  Criteria To Be Used in Decomposing Systems into Modules",
  DOI `10.1145/361598.361623`. Source for keeping change-prone knowledge behind
  a single module boundary.
- [SPEC CITED: academic_paper] Maro, Anjorin, Wohlrab, and Steghofer 2023
  Requirements Engineering, "Why don't we trace? A study on the barriers to
  software traceability in practice", DOI `10.1007/s00766-023-00408-9`. Source
  for keeping rationale and implementation state traceable.
- [SPEC CITED: patent] US Patent Application `US20220253762A1`, "Issue tracking
  systems and methods", published 2022-08-11. Source for linking issue-tracking
  records with external work-management systems.
- [SPEC CITED: technical_doc] `docs/PAPER-TRAIL.md`, reviewed 2026-05-21.
  Source for Paper Trail row fields, the 10-per-session quota, and two-part
  resolution lessons.

[SPEC CITED: feature=fr-paper-trail-handoff-migration kind=academic_paper id=doi:10.1145/361598.361623 verified_at=2026-06-02]
