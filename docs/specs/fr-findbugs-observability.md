# FindBugs Observability-Aware System

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

FindBugs is the always-on static-analysis surface for XF Internal Linker V2.
The default scanner is the deterministic Rust `speccheck find-bugs` binary.
Django is the only writer of `AutoIssue` rows. The Rust MinHash (`papertrail_dedup`)
and locality-sensitive hashing path remains the duplicate-control layer.

The first release adds a dedicated `/find-bugs` operator page, scheduled scans,
artifact retention, observability-aware imports, and a narrow Haskell sidecar
contract for Rust null-state abstract interpretation. The SmolLM2 advisory
model runtime is removed; Windows keeps the Django writer, AutoIssue database
access, Redis broker, Celery scheduling, hooks, and session tooling.

## Sources Of Truth

- Hovemeyer and Pugh 2004, FindBugs bug-pattern catalog discipline, doi:10.1145/1052883.1052895.
- Cousot and Cousot 1977 / abstract interpretation lattice fixpoints, doi:10.1145/512950.512973.
- LLVM source-based coverage documentation for statement and branch coverage.
- VictoriaMetrics single-node documentation for observability stack health and retention.
- ISO/IEC/IEEE 29119-3:2021 for BDD-style test documentation.

## Behavior

Given FindBugs scans the repository, when it emits a confirmed bug candidate,
then Django imports it as `AutoIssue(source="rust_defect")` with dedupe by
canonical fingerprint and C++ near-duplicate matching.

Given the operator clicks `Run FindBugs scan`, when Django starts the scan,
then it executes the Docker-activated Rust binary at
`/opt/xf/compiled/active/speccheck` using the real command shape
`speccheck find-bugs <source-file>`, writes a merged canonical report into the
FindBugs artifact folder, and never uses a Python detector fallback.

Given observability is degraded and a duplicate finding is re-imported, when
Django imports the report, then it avoids duplicate noise and files or updates
one FindBugs-health AutoIssue.

Given artifacts are older than 8 days or total over 1 GB, when the daily prune
runs, then disposable FindBugs files are deleted and protected roots are refused.

Given the monthly knowledge refresh runs, when it summarizes lessons, closed
bugs, and detector effectiveness, then it writes a compact compressed artifact
so history stays useful without becoming another storage problem.

Given `/find-bugs` is opened, when AutoIssues exist, then the page shows open
and closed counts, severity spread, D3 charts, deduped findings, and action
buttons for run, import, prune, and Error Log navigation.

Given FindBugs has recorded model status, when `/find-bugs` loads its summary,
then the operator page can show that the advisory model was intentionally
removed without blocking scanner findings.

Given a FindBugs finding is reviewed, when an agent or operator confirms it as
a real bug, then the row stays in the normal AutoIssue workflow and records the
confirmation in machine-readable metadata.

Given a FindBugs finding is reviewed and is not a real bug, when it is marked
as a false positive or false negative, then the finding resolves and a separate
deduped, compressed learned-lesson row is stored in Postgres for future agents.

Given an operator uses the `/find-bugs` action buttons, when the action is
routine and bounded, then Django performs the action programmatically; manual
command-line use is only for emergency debugging.

The operator page exposes these deliberate actions as real backend calls:
run scan, import latest findings, evaluate with agents, re-evaluate issue,
confirm real bug, mark false positive, mark false negative, move to learned
lessons, create fix task, assign to agent, run duplicate check, run regression
check, approve lesson, sync project context, and generate report. Opening the
Error Log remains a navigation action, not a backend mutation.

Given Haskell sidecar v1 receives Rust AST facts, when variables join through
branches or loops, then the monotonic lattice yields `Definitely Null`,
`Definitely Not Null`, or `Unknown` and terminates because each variable can
ascend at most twice.

Given the SmolLM2 model has been removed, when FindBugs starts a scan, then
Django writes `model.status="removed"` and does not call a model server, local
runner, or Mint helper process.

Given the scanner finds confirmed findings after model removal, when Django
imports the report, then AutoIssue rows are created or updated normally.

## Level A Gate

Any change to `services/speccheck/crates/detectors` or `speccheck find-bugs`
must prove:

- 100% statement coverage.
- 100% decision/branch coverage.
- 100% MC/DC for detector decisions where Boolean conditions exist.
- Object-code analysis smoke through the release binary.
- Zero surviving `cargo-mutants` mutants.

[SPEC CITED: feature=fr-findbugs-observability kind=academic_paper id=doi:10.1145/1052883.1052895 verified_at=2026-06-02]
