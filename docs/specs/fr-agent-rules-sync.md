# FR - Agent Rule Files Sync

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=fr-agent-rules-sync kind=academic_paper id=10.1145/361598.361623-Parnas-1972 verified_at=2026-05-25]
[SPEC CITED: feature=fr-agent-rules-sync kind=technical_literature id=978-0321146533-Beck-2002 verified_at=2026-05-25]

## Problem

The four agent rule files are edited by different tools and have drifted over
time. Shared safety rules must not depend on whichever agent file happened to
be updated first. The shared sections need one manifest, one checker, and one
pre-commit hook so drift is caught before commit.

## Behaviour

Given `CLAUDE.md`, `AGENTS.md`, `CODEX.md`, and `GEMINI.md`.
When a section listed in `docs/agent-rules-sync-manifest.yml` appears in all
four files.
Then the section body must be byte-identical after line-ending normalization.

Given Plan 40, Plan 41, and Plan 42 add Lua ownership, Lua advisor, and C ABI
rules.
When `scripts/sync_agent_rules.py --verify-plan-40-41-42` runs.
Then each required sentence is present in all four files.

Given the shared forbidden phrase list is declared in the manifest.
When `scripts/sync_agent_rules.py --verify-forbidden-phrases` runs.
Then all four files contain the same manifest-listed forbidden phrases.

## Design

The manifest is the source of truth. The checker extracts sections by their
heading text and stops at the next shared-rule heading. This keeps the hook
small, avoids a generated mega-file, and preserves agent-specific sections
outside the manifest.

## Sources

- Parnas 1972, "On the Criteria To Be Used in Decomposing Systems into
  Modules", DOI 10.1145/361598.361623. This supports a single source of truth
  for shared rule boundaries.
- Beck 2002, *Test-Driven Development: By Example*, ISBN 978-0321146533. This
  supports the red-green-refactor workflow used to add the checker.
