# CI Gates — Single Source of Truth

This document tracks every job in `.github/workflows/ci.yml`, whether it
**blocks** merges or is **advisory**, and (for advisory gates) the
written justification required by the `check-no-downgraded-gates`
pre-commit hook.

Update this file whenever a gate's status changes. The pre-commit hook
reads `ci.yml` directly to detect downgrades, but humans (and AI agents)
read this file to understand WHY each gate is where it is.

## Status Legend

| Symbol | Meaning |
|---|---|
| Block | A failure stops the merge. CI fails the PR. |
| Advisory | Failures surface as warnings or artifacts but do not stop merges. Requires a written justification below. |

## Gate Inventory (as of 2026-05-10 prevention sweep)

| # | Job | Status | Notes |
|---|---|---|---|
| 1 | `backend-test` (Django + coverage) | Block | `coverage --fail-under=68` enforces floor. |
| 2 | `frontend-build-and-test` (Angular build + Karma) | Block | Build error or test failure fails CI. |
| 3 | `backend-lint` (ruff) | Block | No escape clause. |
| 4 | `cpp-check` (cppcheck) | Block | `--error-exitcode=1` flag set. |
| 5 | `frontend-lint` (ESLint) | Block | No escape clause. |
| 6 | `frontend-lint-scss` (Stylelint) | Block (after 2026-05-10 hardening) | Was advisory until ~180 legacy hex violations were fixed. Now blocking. |
| 7 | `backend-typecheck` (mypy) | Block | Scoped to `apps/crawler/`; widening planned. |
| 8 | `backend-security` (bandit) | Block | No escape clause. |
| 9 | `python-deps-audit` (pip-audit) | Block | No escape clause. |
| 10 | `frontend-deps-audit` (npm audit, --audit-level=high) | Block | No escape clause. |
| 11 | `docker-compose-validate` | Block | `docker compose config` syntax check. |
| 12 | `semgrep` (security scan, ERROR-only) | Block (after 2026-05-10 hardening) | Was `\|\| true`; now `--severity=ERROR --error` so only ERROR findings fail. WARNING/INFO ride through and upload as artifacts. |
| 13 | `trivy-scan` (CVE scan) | Block (after 2026-05-10 hardening) | Was `exit-code: '0'`; now `exit-code: '1'` with `ignore-unfixed: true` so only fixable HIGH/CRITICAL CVEs fail. |
| 14 | `cpp-format` (clang-format) | Block | `--Werror --dry-run`. |
| 15 | `playwright-e2e` | Block | Test failures fail CI. |
| 16 | `cpp-edge-tests` (test_edges_simsearch + test_edges_scoring) | Block | No escape clause. |
| 17 | `cpp-test` (GoogleTest unit tests) | Block | `ctest --output-on-failure`. |
| 18 | `cpp-asan` (AddressSanitizer) | Block | `ctest --output-on-failure` in ASAN build. |
| 19 | `cpp-tsan` (ThreadSanitizer) | **Advisory** | See justification below. |
| 20 | `missing-tests-check` | Block (after 2026-05-10 hardening) | Was `::warning::`; now `::error::` + `exit 1`. The local pre-commit hook (`.githooks/check-missing-tests.py`) catches the same thing earlier. |
| 21 | `cpp-clang-tidy` (semantic — Phase 3) | Block | `.clang-tidy` WarningsAsErrors covers bugprone-*, cert-*, performance-unnecessary-copy-initialization, accidental-copy/move rules, modernize-use-nullptr/override/equals-default. |
| 22 | `python-mutmut` (Python mutation - Phase 4a) | Block | Scoped to `apps/auto_issues/services/fingerprinting.py` and `apps/pipeline/services/field_aware_relevance.py`; surviving mutants fail via junitxml inspection. |
| 23 | `frontend-stryker` (Angular and JavaScript mutation - Phase 4a) | Block | Scoped to `src/app/core/services/a11y-prefs.service.ts`; `thresholds.break: 95` is the hard floor. |
| 24 | `cpp-mull-fieldrel` (C++ mutation - scoped pilot) | Block | Installs Mull 19, runs only `test_fieldrel`, and fails below the configured mutation threshold. |
| 25 | `go-mutation-tooling` (Go mutation install readiness) | Block | Installs `avito-tech/go-mutesting`; it does not run a broad whole-module mutation gate. |
| 26 | `cpp-libfuzzer-smoke` (libFuzzer 60s/target — Phase 4b) | Block | Three starter targets (fuzz_simsearch / fuzz_scoring / fuzz_passagesim) with `-fsanitize=fuzzer,address,undefined`. Crash reproducers upload as `libfuzzer-crashes` artefact. |
| 27 | `cpp-msan` (MemorySanitizer project-only — Phase 4c) | Block | `-fsanitize-blacklist=msan-ignore.txt` excludes Faiss/Eigen/ICU/TBB/pybind11. Runs only `test_simsearch + test_scoring + test_passagesim`. `MSAN_OPTIONS=halt_on_error=1`. |
| 28 | `super-linter` (Hadolint + GH Actions YAML + Markdown + Bash + Gitleaks — Phase 5) | Block | `super-linter/super-linter@v7` with `ENV_FILE=.github/super-linter.env`. Disables Ruff/ESLint/Stylelint which run as dedicated jobs. |
| 29 | `CodeQL` (per-language security analysis) | Block | Dynamic language detection scans only supported tracked languages, writes one SARIF artifact per language, and files CodeQL-backed AutoIssues through the self-hosted AutoIssue ingest job. |

## Advisory Gate Justifications

### `cpp-tsan` — ThreadSanitizer

**Status:** Advisory.
**Reason:** TBB (Intel Threading Building Blocks) generates a steady stream of false-positive TSAN warnings under its work-stealing scheduler. Real concurrency bugs would be drowned in the noise without a curated suppression file (`tsan.supp`). Writing that suppression file requires running TSAN on Linux against a representative workload — not feasible from the Windows host where most of this project's development happens.

**Plan to remove the advisory:** A future session with Linux access should:
1. Run TSAN locally against the existing test suite + a workload that exercises the autotuner + pipeline (the highest-concurrency code paths).
2. Triage every reported race; for each TBB-internal race, add a `race:^tbb` rule to `tsan.supp`.
3. Confirm a clean run.
4. Wire `--suppressions=tsan.supp` into the CI step and remove `|| true`.
5. Update this file to flip `cpp-tsan` from Advisory to Block.

**`# GATE-DOWNGRADE-JUSTIFICATION:`** TBB false-positive noise; suppression file requires Linux TSAN run before flipping blocking.

## How to Add or Modify a Gate

1. Edit `.github/workflows/ci.yml` to add/modify the job.
2. If the gate is advisory, add `# GATE-DOWNGRADE-JUSTIFICATION: <reason>` near the step. The pre-commit hook (`check-no-downgraded-gates.py`) requires this comment with at least 10 characters after the colon.
3. Update this file to add a row in the Gate Inventory and (for advisory gates) a justification subsection.
4. If the gate replaces or is replaced by a pre-commit hook, cross-reference both directions.

## Why This File Exists

Prior to 2026-05-10, the project had 5 warning-only CI gates that drifted into uselessness because there was no single record of which gates were blocking and which were not. PRs would be merged "clean" while the security scan report uploaded silently and the missing-test check emitted a warning nobody read. This file plus the new `check-no-downgraded-gates.py` hook together close that drift gap.
