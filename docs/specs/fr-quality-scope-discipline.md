# Quality Tool Scope Discipline

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Summary

Local quality tools must run only on an explicit list of files or test binaries
derived from the current Git diff. If a tool cannot determine its scope, it
skips in local mode instead of scanning the whole repository. If the scope is
larger than that tool's local limit, the wrapper refuses the run, records one
deduped AutoIssue, and leaves the whole-tree run to continuous integration.

## Behavior

Given a wrapper sees no changed files for its language, when it prepares the
quality command, then it writes one scope-decision line with
`decision="skipped"` and does not invoke the heavy tool.

Given a wrapper sees more targets than the tool's local cap, when it enforces
the cap, then it prints a clear failure message, writes one scope-decision line
with `decision="refused"`, and files one AutoIssue with the external id
`scope_cap_exceeded::<wrapper>::<tool>`.

Given `XF_QUALITY_ENV=ci` and `XF_SCOPE_FULL_TREE=1`, when a wrapper asks to run
a larger scope, then the cap is bypassed and the scope-decision line records
`reason="ci_full_tree_opt_in"`.

Given `XF_QUALITY_ENV=ci` without `XF_SCOPE_FULL_TREE=1`, when a wrapper asks to
run a larger scope, then the normal cap still applies.

Given a wrapper logs scope, when it appends to `audit/scope_decisions.jsonl`,
then it writes one JSON object per decision so later agents can see why a tool
ran, skipped, or refused.

## Design

- `scripts/commit_scope.py` remains the source of changed-file scope for local
  and push checks.
- `scripts/quality_cores.py` is the Python reference for adaptive worker counts.
  It uses every visible logical processor by default, honors a positive
  `XF_QUALITY_CORES` override, clamps that override to visible CPUs, and prints
  the standard `[quality_cores] ...` line for auditability.
- `scripts/quality_cores.sh` mirrors the same policy for shell wrappers, while
  Go and Rust carry tiny local equivalents for native wrapper tests.
- `scripts/mutation_policy.sh` owns the common mutation command surface:
  incremental by default, full only with `--full` or `XF_MUTATION_FULL=1`,
  no full mutation inside hook contexts, and standard mutation log fields for
  mode, subsystem, workers, schemata, and coverage.
- `scripts/scope_cap.py` owns cap checks so Python tests can exercise the same
  rules the shell wrappers use.
- `scripts/_quality_concurrency.sh` owns shell adapters:
  `quality_enforce_cap` and `quality_log_scope_decision`.
- Wrappers pass explicit target lists into tools. Empty target lists never
  become `.` or a broad project folder.
- Scope-cap AutoIssues use one stable external id per wrapper and tool. Repeats
  increase the existing row's occurrence count instead of creating many rows.
- The scope log is append-only. Rotation is an explicit management command, not
  automatic cleanup.
- The repo-wide quality lock remains serial. Inside one locked wrapper, tools
  may use all visible workers.

## Initial Caps

| Tool | Local cap |
|---|---:|
| mutmut | 20 files |
| Stryker | 20 files |
| Mull | 7 binaries |
| go-mutesting | 20 files |
| pytest | 50 files |
| Angular test | 50 files |
| CTest | 10 binaries |
| ruff | 200 files |
| pylint | 200 files |
| mypy | 200 files |
| bandit | 200 files |
| ESLint | 200 files |
| Stylelint | 200 files |
| clang-tidy | 50 files |
| clang-format | 200 files |
| golangci-lint | 200 files |
| Coverage | 100 files |
| libFuzzer | 5 targets |

## Sources

- [SPEC CITED: technical_doc] Git project, "diff-options Documentation,"
  reviewed 2026-05-20. https://git-scm.com/docs/diff-options
- [SPEC CITED: technical_doc] Python Software Foundation, "argparse - Parser
  for command-line options, arguments and subcommands," Python 3.12
  documentation, reviewed 2026-05-20.
  https://docs.python.org/3.12/library/argparse.html
- [SPEC CITED: technical_doc] Django Software Foundation, "Writing custom
  django-admin commands," reviewed 2026-05-20.
  https://docs.djangoproject.com/en/dev/howto/custom-management-commands/
- [SPEC CITED: technical_doc] JSON Lines, "JSON Lines text file format,"
  reviewed 2026-05-20. https://jsonlines.org/
- [SPEC CITED: technical_doc] Python Software Foundation, "`os.cpu_count` and
  `os.sched_getaffinity` documentation," reviewed 2026-05-25.
  https://docs.python.org/3/library/os.html
- [SPEC CITED: technical_doc] Linux kernel documentation, "cgroup v2 `cpu.max`
  CPU bandwidth control," reviewed 2026-05-25.
  https://docs.kernel.org/admin-guide/cgroup-v2.html

## Test Plan

- `python -m pytest -q scripts/test_scope_cap.py`
- `python -m pytest -q scripts/test_scope_audit.py`
- `python -m pytest -q scripts/test_detect_changed_modules.py`
- `python -m pytest -q scripts/test_select_python_test_targets.py`
- `python -m pytest -q scripts/test_cpp_mutation_targets.py`
- `docker compose exec -T backend python -m pytest -p randomly -q --reuse-db apps/auto_issues/tests/test_scope_cap_autoissue.py`

[SPEC CITED: feature=fr-quality-scope-discipline kind=technical_doc id=https://git-scm.com/docs/diff-options verified_at=2026-06-02]
