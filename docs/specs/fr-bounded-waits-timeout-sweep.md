# Bounded Waits Timeout Sweep

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Summary

Repository-owned commands, checks, tests, browser waits, service calls, and build
helpers must use explicit time limits when they wait on an external process,
network service, browser state, or remote procedure call. A timeout must fail in
plain English and leave enough report text for the next agent to understand what
stopped.

## Behavior

Given a quality helper starts a command, when that command exceeds its time
limit, then the helper writes a report that says how many seconds elapsed and
returns exit code 124.

Given a Git-scope helper reads changed files, when Git is unavailable or takes
too long, then the helper returns an empty result instead of waiting forever.

Given a browser test opens a page, when the page has live network polling, then
the test waits for visible page content rather than network quiet.

Given compiled artifacts are built in Docker, when the compiler or import check
hangs, then the script stops after its documented build or import budget.

## Defaults

- Git and small hook reads: 10 seconds.
- Hook database verifier calls: keep existing 60-second timeout.
- Local quality tool steps: 300 seconds.
- Python dependency audits: 300 seconds.
- Compiled builds: 1800 seconds, override with
  `XF_COMPILED_BUILD_TIMEOUT_SECONDS`.
- Compiled import checks: 60 seconds, override with
  `XF_COMPILED_IMPORT_TIMEOUT_SECONDS`.

## Test Plan

- `python -m pytest -q scripts/test_run_quality_step.py`
- `python -m pytest -q scripts/test_commit_scope.py`
- `python -m pytest -q scripts/test_precommit_docker.py`
- `python -m pytest -q tests/test_bounded_waits.py`
- `python -m pytest -q tests/test_frontend_wait_patterns.py`

## Citations

- Python Software Foundation, `subprocess` documentation, Python 3.12.
  Source for the `timeout` parameter and `TimeoutExpired`.
  https://docs.python.org/3.12/library/subprocess.html
- Requests project, "Timeouts" advanced usage documentation. Source for
  explicit HTTP client timeouts. https://requests.readthedocs.io/
- Playwright documentation, auto-waiting and assertions. Source for waiting on
  visible UI state instead of network quiet. https://playwright.dev/docs/actionability
- GNU Coreutils manual, `timeout` invocation. Source for exit code 124 after a
  timed-out command. https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html
- gRPC documentation, "Deadlines". Source for finite remote-call deadlines.
  https://grpc.io/docs/guides/deadlines/

[SPEC CITED: feature=fr-bounded-waits-timeout-sweep kind=technical_doc id=https://docs.python.org/3.12/library/subprocess.html verified_at=2026-06-02]
