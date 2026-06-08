# Coverage Gap Test Cases

These test cases support `docs/specs/fr-rust-speccheck.md` and bound the
`speccheck coverage-gaps` implementation.

## LCOV uncovered line

Given an LCOV file contains `SF:apps/foo/services/bar.py` and `DA:42,0`
When the operator runs `speccheck coverage-gaps --format lcov <path>`
Then the JSON report contains one `bug_candidates` row with
`bug_pattern_id="RUSTBUG-COVERAGE-001"`, `category="coverage_gap"`,
`file="apps/foo/services/bar.py"`, and `line=42`.

## LCOV uncovered branch

Given an LCOV file contains `BRDA:43,0,0,0`
When the operator runs `speccheck coverage-gaps --format lcov <path>`
Then the JSON report contains one high-priority coverage gap for line 43.

## Cobertura uncovered line

Given a Cobertura report contains `<class filename="apps/foo/services/bar.py">`
and a `<line number="42" hits="0"/>` element
When the operator runs `speccheck coverage-gaps --format cobertura <path>`
Then the JSON report contains one importable coverage-gap finding for that file
and line.

## Stub generation

Given a coverage gap exists at `apps/foo/services/bar.py:42`
When the operator runs `speccheck coverage-gaps --format lcov --stubs-dir <dir> <path>`
Then `speccheck` writes a human-editable stub file under `<dir>` with an
`AUTO-GENERATED-STUB` marker and a Given/When/Then comment block.

## Malformed input

Given a coverage file is malformed
When the operator runs `speccheck coverage-gaps`
Then the command exits with a plain-English error on stderr and does not write a
partial JSON report.

## cargo-mutants survivor

Given a cargo-mutants `outcomes.json` file contains a `missed` mutant for
`crates/foo/src/lib.rs:42`
When the operator runs `speccheck coverage-gaps --format cargo-mutants <path>`
Then the JSON report contains one `bug_candidates` row with
`bug_pattern_id="RUSTBUG-MUTATION-001"`, `category="mutation_survivor"`,
`kind="surviving_mutant"`, and `line=42`.
