# AutoIssue Native Retrieval And Correctness Oracle

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

AutoIssue filing stays in Django because Django owns the database writes,
transactions, permissions, and audit history. Slow read-heavy AutoIssue paths
may move to a compiled read model only after profiling proves the Python path is
hot. The compiled path is split by responsibility:

- Rust owns fast retrieval, filtering, fingerprint grouping, and bounded JSON
  parsing for AutoIssue read models.
- Haskell owns narrow logical correctness checks where a pure rule can confirm
  whether a candidate state is valid, invalid, or unknown.
- Python remains the orchestrator, database writer, and fallback reference path.
- Existing C++ scoring kernels are not replaced or imported. This feature does
  not touch candidate scoring, similarity math, ranking math, or embedding
  loops, so it does not clash with the C++ first compute-path rule.

## Sources Of Truth

- Amdahl 1967, "Validity of the Single Processor Approach to Achieving Large
  Scale Computing Capabilities", doi:10.1145/1465482.1465560.
- Little 1961, "A Proof for the Queuing Formula: L = lambda W",
  doi:10.1287/opre.9.3.383.
- Hovemeyer and Pugh 2004, "Finding Bugs is Easy",
  doi:10.1145/1052883.1052895.
- Ayewah et al. 2008, "Using Static Analysis to Find Bugs",
  doi:10.1109/MS.2008.130.
- Broder 1997, "On the resemblance and containment of documents",
  doi:10.1109/SEQUEN.1997.666900.
- Indyk and Motwani 1998, "Approximate nearest neighbors",
  doi:10.1145/276698.276876.
- RFC 8259 for JSON interchange.
- RFC 6234 for SHA-256 fingerprinting.
- The Rust Reference and The Cargo Book for Rust semantics and workspace
  packaging.
- PyO3 official user guide for Rust/Python extension boundaries when a native
  Python module is used.
- Haskell 2010 Report for the pure correctness sidecar language semantics.
- Existing repository specs:
  `docs/specs/fr-rust-speccheck.md`,
  `docs/specs/fr-findbugs-observability.md`, and
  `docs/specs/fr-native-inspection-and-spec-windows.md`.

## Profiling Baseline

Measured on 2026-05-23 with:

```text
docker compose exec -T backend python -m pytest -q --reuse-db apps/auto_issues --durations=30
```

The run produced useful duration data but did not pass because unrelated quota
expectations and one FindBugs missing-model expectation are already failing.
The slowest measured AutoIssue paths were:

- `tests_findbugs_operational.py::test_missing_smollm2_runner_or_model_files_health_issue`
  at 26.57 seconds.
- `tests_views.py::AutoIssueAPITests::test_resync_returns_picker_results_for_admin`
  at 9.07 seconds.
- `tests/test_drain_findings_buffer.py` drain cases at about 1.47 to 2.16
  seconds each.
- `tests_import_rust_findings.py::RustFindingsImportTests::test_import_accepts_all_35_speccheck_bug_patterns_idempotently`
  at 1.65 seconds.
- Several direct filing command tests at about 0.8 to 2.1 seconds.

This profile does not yet justify a blanket rewrite. Amdahl's law means native
work must target the measured slow fraction, and Little's law means queue-facing
work should reduce time spent per item before increasing worker concurrency.

## Native Boundary

Rust may be introduced only for read-heavy work with stable, serializable inputs:

- import report normalization before Django writes rows;
- candidate retrieval for `print_open_issues` and picker views;
- duplicate grouping over already-fetched row summaries;
- source-observation normalization and capping;
- stable fingerprint and repeat-key computation.

Rust must not:

- write AutoIssue rows directly;
- replace Django transactions;
- import Django models;
- duplicate C++ scoring kernels;
- own ranking or embedding math;
- call Haskell for every row when a simple Rust predicate is enough.

Haskell may be introduced only as a pure correctness oracle for small JSON
states. It returns one of:

- `valid`
- `invalid`
- `unknown`

Haskell must not write database rows, call Django models, or make network calls.
Python decides whether an `invalid` result becomes an AutoIssue.

## Required Behavior

Given a profiled AutoIssue retrieval path takes more than 500 ms in a focused
test or more than 5 seconds in an end-to-end test, when the path is read-heavy
and its inputs can be represented as bounded JSON, then a Rust read-model helper
may replace the Python loop after a parity test exists.

Given Rust returns retrieval results, when Python compares them with the current
Python reference implementation on the same fixture, then titles, ids,
fingerprints, categories, priorities, and source counts must match exactly.

Given Haskell receives a small correctness state from Rust or Python, when the
state is complete and valid, then Haskell returns `valid`; when the state is
provably contradictory, it returns `invalid`; when required facts are missing,
it returns `unknown`.

Given a native binary or extension is missing, when the AutoIssue workflow runs,
then Python uses the reference path and files or updates one health AutoIssue
instead of silently claiming the native path is live.

Given a native helper is added, when Docker quality runs, then Rust and Haskell
tests, lint, coverage, mutation/fuzz readiness, and benchmark wiring are
discoverable through the Docker-managed compiled-language path.

## Performance Contract

Each native replacement needs four numbers in the handoff before it can ship:

- Python baseline command and time.
- Rust/Haskell command and time.
- Speedup ratio.
- Parity test command.

Minimum acceptance:

- Read-model helpers over more than 100 rows: at least 3x faster than Python.
- JSON report normalization over more than 1,000 findings: at least 3x faster
  than Python.
- End-to-end workflow with database writes: native helper must reduce total wall
  time by at least 20 percent, because database time may dominate.

If a path misses these floors, keep Python as default and file a native-rewrite
follow-up instead of landing a slower or more complex replacement.

## Test Cases

Given a fixture with open, picked, and resolved AutoIssues,
when the Rust retrieval helper groups candidate rows,
then its JSON output matches the Python reference output exactly.

Given a fixture with duplicate canonical fingerprints,
when the Rust grouping helper runs,
then it returns one representative plus duplicate counts matching the Python
reference.

Given a malformed JSON report,
when the Rust report normalizer runs,
then it exits with a structured parse error and Python writes no partial rows.

Given a complete AutoIssue correctness state,
when the Haskell oracle receives it,
then it returns `valid`.

Given a state says a row is `open` and also has a non-null `resolved_at`,
when the Haskell oracle receives it,
then it returns `invalid`.

Given required fields are missing,
when the Haskell oracle receives the state,
then it returns `unknown` and Python does not file a correctness AutoIssue.

Given the native helper is unavailable,
when the same workflow runs,
then Python returns the same business result and files one native-health
AutoIssue.

## Current Decision

The first profile identified candidates, and the first focused fix showed that
the API resync picker slowdown was database query shape rather than Python loop
speed. The pre-fix cProfile for
`apps/auto_issues/tests_views.py::AutoIssueAPITests::test_resync_returns_picker_results_for_admin`
showed 56 `score_candidate` calls spending about 0.208 seconds in the scoring
path. After replacing per-candidate regression lookups with one batched
regression lookup, the same focused profile showed `score_candidates` at about
0.008 seconds, with 56 pure arithmetic score applications behind one query.

That result does not justify a Rust/Haskell replacement for scoring. Per this
spec, Python remains the default when a query-shape fix removes the measured
hot fraction without adding a compiled-language boundary.

The Rust findings import occurrence-count path followed the same rule. The
focused test
`apps/auto_issues/tests_import_rust_findings.py::RustFindingsImportTests::test_import_accepts_all_35_speccheck_bug_patterns_idempotently`
showed 70 repeated `_next_occurrence_count` lookups at about 0.315 seconds
before the fix. After replacing those per-candidate lookups with two
`_existing_occurrence_counts` batch lookups across the two report imports, the
same lookup work measured about 0.010 seconds and the focused test wall time
moved from 38.30 seconds to 27.14 seconds. The import path already uses the
existing compiled dedup index for similarity, so adding a new Rust or Haskell
boundary for this database lookup would not address the measured bottleneck.

Remaining focused profiles before any native replacement:

- FindBugs missing-model path after the model-server fix.
- findings-buffer drain path only if a larger buffer fixture proves the command,
  not Django test startup, is the limiting cost.
- Rust findings import similarity indexing only if a larger fixture shows the
  existing compiled dedup index, not database upserts, is the limiting cost.

Only after those focused profiles isolate a Python loop should Rust replace that
specific loop.

[SPEC CITED: feature=fr-autoissue-native-retrieval kind=academic_paper id=doi:10.1145/1465482.1465560 verified_at=2026-06-02]
