# Rust Spec-to-Test Checker

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

`speccheck` is a Docker-managed Rust command-line checker. It reads repository
files, parses strict `Given / When / Then` behavior blocks, finds low-noise bug
patterns, and writes canonical JSON reports. It never writes to the database.
Django remains the only writer of `AutoIssue` rows through
`manage.py import_rust_findings`.

The checker is deliberately narrow because it feeds the same issue queue agents
read at session start. A noisy checker would make the repair queue less useful,
so Rust code is treated as mission-critical: no `unsafe`, strict linting, 100%
line and branch coverage, mutation testing, fuzz harnesses for parsers, and a
Docker-only toolchain.

## Sources Of Truth

- Beck 2002, *Test Driven Development: By Example*, ISBN 978-0321146533.
- Beck 1999, *Extreme Programming Explained*, doi:10.1109/2.796139.
- Crispin and Gregory 2009, *Agile Testing*, ISBN 978-0321534460.
- Parnas 1972, "On the Criteria To Be Used in Decomposing Systems into Modules", doi:10.1145/361598.361623.
- Hovemeyer and Pugh 2004, "Finding Bugs is Easy", doi:10.1145/1052883.1052895.
- Ayewah et al. 2008, "Using Static Analysis to Find Bugs", doi:10.1109/MS.2008.130.
- Broder 1997, "On the resemblance and containment of documents", doi:10.1109/SEQUEN.1997.666900.
- Indyk and Motwani 1998, "Approximate nearest neighbors", doi:10.1145/276698.276876.
- DeMillo, Lipton, and Sayward 1978, "Hints on Test Data Selection", doi:10.1109/C-M.1978.218136.
- Jia and Harman 2011, "An Analysis and Survey of the Development of Mutation Testing", doi:10.1109/TSE.2010.62.
- RFC 8259 for JSON, RFC 6234 for SHA-256, ISO/IEC/IEEE 29119-3:2021 for test documentation, ISO/IEC/IEEE 29148:2018 for requirements.
- LCOV/gcov tracefile format for line and branch coverage exports.
- Cobertura XML coverage report shape, including `class filename`, `line number`, `hits`, `branch`, and `condition-coverage` fields.
- cargo-mutants `mutants.out` directory documentation, including `outcomes.json`
  and the `missed` / `timeout` outcome files.
- Official docs: The Rust Reference, The Cargo Book workspace documentation, cargo-llvm-cov, cargo-mutants, cargo-fuzz, RustSec/cargo-audit, cargo-deny, criterion, proptest, and insta.

## Architecture

```text
docs/specs + handoff + code exports
          |
          v
services/speccheck/ Rust crates
 parser -> repeat_key -> detectors -> report -> cli
          |
          v
canonical JSON report
          |
          v
Django import_rust_findings command
          |
          v
AutoIssue(source="rust_defect") -> Error Log "Bug Patterns" tab
```

## Workspace

The Rust workspace lives under `services/speccheck/` and has one crate per
public surface:

- `parser`: strict `Given / When / Then` extraction.
- `repeat_key`: deterministic repeat keys.
- `report`: canonical JSON report building.
- `detectors`: FindBugs-style detector registry and initial pattern metadata.
- `coverage`: coverage and mutation gap shapes.
- `host_fingerprint`: host-change fingerprint inputs.
- `cli`: command-line entrypoint.

## Runtime Binary Contract

`speccheck` is a compiled runtime tool, so the runnable binary must be built in
the Docker-managed `compiled-tools` container and activated through the shared
compiled-artifact store:

- source hash: Cargo workspace files under `services/speccheck/`;
- build command: `cargo build --release --locked --bin speccheck`;
- active path: `/opt/xf/compiled/active/speccheck`;
- store path: `/opt/xf/compiled/store/<sha256>`;
- manifest key: `active.rust_speccheck`.

Given the compiled-tools container starts, when the Rust source hash changes,
then `scripts/ensure_compiled_artifacts.py` rebuilds `speccheck`, verifies the
binary can run, stores one content-addressed copy, and activates it for backend
and Celery containers. Given the backend container starts without Cargo, when
the active Rust binary already exists, then startup reuses it instead of trying
to run a host-only build. Given the active binary is missing, when FindBugs is
run, then Django files a health AutoIssue rather than falling back to Python.

## JSON Report Contract

Reports have seven top-level sections:

```json
{
  "metadata": {},
  "parsed_behaviors": [],
  "test_case_candidates": [],
  "bug_candidates": [],
  "duplicate_warnings": [],
  "stale_record_warnings": [],
  "summary": {}
}
```

Every `bug_candidates` row imported into Django must include:

- `bug_pattern_id`
- `title`
- `description`
- `severity`
- `category`
- `file`
- `line`
- `evidence`
- `suggested_fix`
- `confidence`
- `citation`
- `fingerprint`
- `priority_score`

Missing fields reject the whole report so no partial rows are created.

## FindBugs-Style Detector Contract

`speccheck find-bugs <path>` is the compiled Rust path for low-noise static bug
pattern checks. The detector catalog follows Hovemeyer and Pugh 2004: each
pattern has a stable ID, category, severity, confidence, evidence, suggested
fix, citation, and fingerprint. The first release includes the 35 planned
static IDs and must detect both single-line evidence and small source-context
evidence where the risk depends on a surrounding block.

Context-sensitive detector behavior in this slice:

- `RUSTBUG-PERF-001` fires when a loop body performs
  `.objects.filter(...).first()`, because that can create one database query
  per parent row.
- `RUSTBUG-PERF-004` fires when an `async def` block performs `requests.get(`,
  because that blocks the async worker.
- `RUSTBUG-PERF-008` fires when a loop body calls `.save()`, because that can
  create one database write per item.
- `RUSTBUG-CONC-005` fires when an `async def` block performs a synchronous
  Django ORM call such as `.objects.get(`.

These checks are conservative. They require clear surrounding context and do not
try to execute source text. Findings point at the risky operation line rather
than the block header so the operator lands on the code that needs the fix.

## Coverage And Mutation Gap Contract

`speccheck coverage-gaps` is the compiled Rust path for Block H coverage-gap
work. It ingests coverage reports, emits one `bug_candidates` row per stable
gap cluster, and optionally writes a suggested test stub under a caller-provided
directory. It does not call Python to parse the report and it does not write
database rows.

Supported report inputs in this slice:

- LCOV: `SF:<path>` starts a source file, `DA:<line>,0` marks an uncovered line,
  and `BRDA:<line>,...,0` or `BRDA:<line>,...,-` marks an uncovered branch.
- Cobertura XML: `<class filename="...">` names the source file, `<line
  number="..." hits="0">` marks an uncovered line, and `<line branch="true"
  condition-coverage="not 100%">` marks an uncovered branch.
- cargo-mutants `outcomes.json`: `missed` and `timeout` outcomes become
  `surviving_mutant` gaps. The parser accepts common nested shapes such as
  `mutant.file` plus `mutant.line` and `mutant.span.file` plus
  `mutant.span.start.line`, because cargo-mutants documents the output as
  machine-readable but warns the exact file format can change.

Coverage gap rows use `bug_pattern_id="RUSTBUG-COVERAGE-001"`,
`category="coverage_gap"`, `confidence="high"`, and a stable fingerprint shaped
as `coverage:<file>:<line_start>:<kind>`. Uncovered branches are `severity=high`
with `priority_score=2.0`; uncovered lines are `severity=medium` with
`priority_score=1.0`. Mutation survivor rows use
`bug_pattern_id="RUSTBUG-MUTATION-001"`, `category="mutation_survivor"`,
`severity="high"`, `priority_score=3.0`, and a stable fingerprint shaped as
`mutation:<file>:<line_start>:surviving_mutant`.

When `--stubs-dir <dir>` is supplied, the Rust binary writes one
`AUTO-GENERATED-STUB` file per gap. Stub filenames are repo-path based, for
example `apps/foo/services/bar.py:42` becomes
`apps_foo_services_bar_42.py`. Each stub contains a plain `Given / When / Then`
comment block plus a failing test function placeholder. The generated stub is a
human-editable suggestion, not an auto-passing test.

## Exit Codes

- `0`: report created and policy passed.
- `1`: findings were produced.
- `2`: invalid command or invalid configuration.
- `3`: malformed input report.
- `4`: path escaped the repository root.

## BDD Contract

Given a spec contains one well-formed behavior block,
when `speccheck scan` runs,
then the JSON report contains one parsed behavior and zero diagnostics.

Given a report contains one bug candidate,
when `python manage.py import_rust_findings --report <path>` runs twice,
then one `AutoIssue(source="rust_defect")` row exists and its occurrence count is
`2`.

Given an operator opens `/error-log#bug-patterns`,
when Rust defect rows exist,
then the Error Log shows the Bug Patterns tab filtered to `source=rust_defect`.

Given an LCOV report has `DA:42,0` under `SF:apps/foo/services/bar.py`,
when `speccheck coverage-gaps --format lcov <report>` runs,
then stdout contains a canonical JSON report with one coverage-gap bug
candidate for `apps/foo/services/bar.py:42`.

Given a Cobertura report has a branch line whose `condition-coverage` is less
than `100%`,
when `speccheck coverage-gaps --format cobertura <report>` runs,
then stdout contains a coverage-gap bug candidate with `kind=uncovered_branch`,
`severity=high`, and `priority_score=2.0`.

Given a coverage report has a gap and the operator supplies `--stubs-dir`,
when `speccheck coverage-gaps` runs,
then the binary writes an `AUTO-GENERATED-STUB` file containing `Given`, `When`,
and `Then` guidance while keeping stdout as JSON only.

Given a cargo-mutants `outcomes.json` report contains a `missed` mutant at
`crates/foo/src/lib.rs:42`,
when `speccheck coverage-gaps --format cargo-mutants <report>` runs,
then stdout contains one mutation-survivor bug candidate with
`bug_pattern_id="RUSTBUG-MUTATION-001"` and `category="mutation_survivor"`.

Given a coverage report path is malformed or the stub directory cannot be
created,
when `speccheck coverage-gaps` runs,
then the binary exits non-zero with a plain-English error and does not emit a
partial success claim.

## Safety Rules

Rust code is read-only in this release. It may read files inside `repo_root`,
write JSON reports to explicit output paths, and write ignored runtime baselines.
It must not connect to the database, execute spec text, follow paths outside the
repository root, print secrets, or hold long-lived sockets.

Every crate root uses `#![forbid(unsafe_code)]`. Any future foreign-function
code must live in a separate reviewed module and carry a new source-backed spec.

[SPEC CITED: feature=fr-rust-speccheck kind=technical_literature id=978-0321146533-Beck-2002 verified_at=2026-06-02]
