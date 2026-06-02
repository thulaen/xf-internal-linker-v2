# Hook Finding To AutoIssue

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Summary

Hook findings must become real AutoIssue rows. When Docker or the backend is
not reachable, the hook writes one JSON line to `audit/findings_buffer.jsonl`
so the finding can be filed at the next session start. Helper crashes must be
visible in `audit/helper_failures.jsonl` and in the hook's standard error.

## Behavior

Given a hook finds a problem and the backend is healthy, when
`file_finding_as_autoissue` is called, then the backend creates or updates one
AutoIssue row with `source="agent"` and an external id based on the category and
fingerprint.

Given the backend is unreachable, when the helper is called, then the finding is
appended to the buffer file as one JSON object plus a newline and the hook keeps
running.

Given the backend filing command returns a failure status, when the helper falls
back to the buffer file, then it also writes one visible helper-failure record
with the backend's error text so the failure is not silent.

Given the helper has crashed more than five times in the last sixty minutes,
when another hook tries to file a finding, then the helper raises a hard-stop
sentinel so the calling hook can fail loudly until the crash rate clears.

Given `XF_QUALITY_ENV=ci`, when a hook tries to use soft filing, then the helper
raises a hard-stop sentinel and writes nothing, because remote quality runs must
stay strict.

Given the buffer contains valid JSON lines, when `manage.py drain_findings_buffer`
runs and the backend is healthy, then the command files or dedupes each finding,
rotates the old buffer, and creates a fresh empty buffer file.

Given pre-commit hooks file one or more findings, when the pre-commit driver
finishes successfully, then the driver writes the filed AutoIssue IDs to a
per-repository transcript under `/tmp`.

Given Git invokes `prepare-commit-msg`, when that transcript contains one or
more finding IDs, then the hook appends one footer line to the commit message
file and removes the transcript. When the transcript is missing or empty, the
message file is unchanged.

Given an agent finishes a commit attempt, push attempt, or edit-only turn, when
it replies in chat, then it uses the matching standard outcome template from
`AGENTS.md` without extra prose before or after the template.

Given a hard pre-commit hook refuses a commit, when
`scripts/precommit-docker.sh` records the non-zero result, then the driver files
or dedupes one `source="agent"` AutoIssue with category `commit_blocker`,
severity `high`, the full hook output in the description, and the hook's plain
reason plus unblock suggestion in `lessons_learned`.

Given the same hard pre-commit hook fails again with the same failure
fingerprint, when the driver files the commit blocker, then the existing
AutoIssue occurrence count goes up instead of creating a duplicate row.

Given only soft local checks file findings, when the driver finishes, then no
`commit_blocker` AutoIssue is filed and the commit driver continues through the
normal soft-finding path.

Given a GitHub Actions workflow run finishes with `conclusion=failure`, when the
CI failure workflow runs, then it reads the failed run's jobs through `gh api`
and files one `source="gh_ci"` AutoIssue per failed job.

Given a failed CI job is filed, when the next session reads open AutoIssues, then
the AutoIssue description includes the GitHub Actions run URL and the lesson
text starts with `Trap: CI failed at <step> with output <excerpt>; see run
<url>`.

Given the same workflow job fails again with the same error fingerprint, when the
CI failure command runs again, then the existing AutoIssue occurrence count goes
up and the new run id is appended to `source_observations` instead of creating a
duplicate row.

Given a GitHub Actions failure is filed as an AutoIssue, when
`manage.py file_ci_failure` completes, then it also appends one JSON line to
`audit/github_actions_failures.jsonl` with the run id, workflow, branch,
commit, failed job, run URL, AutoIssue id, and `status="open"`.

Given the GitHub Actions failure history has open rows after the previous
handoff timestamp, when `manage.py print_failed_github_actions --since-handoff`
runs, then it prints one `[GH ACTIONS READ: ...]` marker with the count and up
to three picked run ids.

Given a `source="gh_ci"` AutoIssue changes to `status="resolved"`, when the row
is saved, then one resolved JSON line is appended to
`audit/github_actions_failures.jsonl` for each run id recorded on that issue.

Given the operator wants a failure trend, when
`manage.py print_failed_github_actions --trend --top N` runs, then output is
grouped by workflow and failed job name, sorted by failure count, and capped at
`N` groups.

Given the failure history grows too large, when
`manage.py rotate_gh_actions_log --before YYYY-MM-DD` is explicitly invoked,
then rows older than that date move into yearly archive files and the active log
keeps the remaining rows. No scheduled task rotates or deletes it.

Given the GitHub Actions failed-run picker cannot read its app setting, when it
falls back to the default setting value, then it logs the setting key and the
failure so the fallback is visible during AutoIssue review.

Given the scoped mutation workflow finds surviving mutants, when its existing
mutation filing command runs, then it keeps filing `source="mutation"` rows and
the CI failure workflow does not change that path.

## Design

- `.githooks/_hook_helpers.py` validates hook finding inputs before any file or
  database write.
- The hook helper shells a single backend command,
  `manage.py file_hook_finding`, using list-form arguments. The command accepts
  optional explicit lessons so special callers such as commit-blocker filing can
  store `Trap:` and `Fix shape:` text without a placeholder.
- The backend command owns AutoIssue row creation, category creation, repeat
  detection, and tag derivation.
- The buffer writer uses low-level `os.open` with append mode so concurrent hook
  callers write complete lines without seeking over each other.
- The drain command reads the current buffer, writes malformed lines to
  `audit/findings_buffer.errors.jsonl`, routes valid lines through the same
  backend filing function, renames the processed buffer, and creates a fresh
  empty buffer.
- `scripts/precommit-docker.sh` owns hook execution order, records every
  successful finding marker, and prints one final summary line.
- `scripts/precommit-docker.sh` also owns hard-block capture. A small
  `_file_commit_blocker` helper extracts the hook reason and unblock suggestion,
  calls `manage.py file_hook_finding` with category `commit_blocker`, passes a
  stable external id based on hook name plus failure fingerprint, passes
  explicit `Trap:` and `Fix shape:` lessons, and returns the AutoIssue id for
  the `[COMMIT BLOCKED: ...]` marker.
- `.githooks/prepare-commit-msg` edits the commit message file in place, using
  Git's supported hook timing after the default message exists and before the
  editor opens.
- `AGENTS.md` owns the chat notification templates for commit success, commit
  blocked, push success, push failure, and edit-only turns.
- `CLAUDE.md`, `CODEX.md`, and `GEMINI.md` point to the `AGENTS.md` section so
  future agent-specific rule files do not drift from the shared format.
- `manage.py file_ci_failure` owns job-level GitHub Actions failure filing. It
  uses `source="gh_ci"`, category `ci_job_failure`, and an external id shaped as
  `ci_failure::<workflow>::<job>::<error fingerprint>`.
- `scripts/enumerate_failed_jobs.py` owns the GitHub API read and prints one
  shell-safe argument vector per failed job. The workflow pipes those vectors to
  `manage.py file_ci_failure`.
- `.github/workflows/ci-failure-to-autoissue.yml` is triggered by
  `workflow_run` completion for `CI` and `Scoped Mutation (CI)`. The job is
  gated to failed conclusions only and runs on the self-hosted app runner so
  `docker compose exec -T backend ... file_ci_failure` writes into the real
  AutoIssue database instead of a throwaway runner database. The filing step
  declares `shell: bash` because the self-hosted runner may be Windows and the
  step uses Bash syntax.
- `apps.auto_issues.services.gh_actions_history` owns the append-only JSON-lines
  writer, failure reader, trend grouping, and explicit rotation helper.
- `manage.py print_failed_github_actions --since-handoff` reads the newest
  `AGENT-HANDOFF.md` header through the existing session boundary helper and
  filters open history rows newer than that timestamp.
- `.githooks/check-gh-actions-read.py` enforces the `[GH ACTIONS READ: ...]`
  handoff marker after `[SNAPSHOTS READ: ...]` for code-changing commits.
- `manage.py rotate_gh_actions_log` has no timer or schedule. It only moves old
  history rows when a human or agent invokes it with an explicit cutoff date.

## Sources

- [SPEC CITED: technical_doc] Django Software Foundation, "QuerySet API
  reference: get_or_create and update_or_create," 2026.
  https://docs.djangoproject.com/en/6.0/ref/models/querysets/
- [SPEC CITED: technical_doc] Django Software Foundation, "How to create custom
  django-admin commands," 2026.
  https://docs.djangoproject.com/en/dev/howto/custom-management-commands/
- [SPEC CITED: technical_doc] Python Software Foundation, "os — Miscellaneous
  operating system interfaces," 2026.
  https://docs.python.org/3/library/os.html
- [SPEC CITED: technical_doc] JSON Lines, "JSON Lines text file format," 2026.
  https://jsonlines.org/
- [SPEC CITED: technical_doc] Git project, "githooks Documentation:
  prepare-commit-msg," reviewed 2026-05-20.
  https://git-scm.com/docs/githooks
- [SPEC CITED: technical_doc] Git project, "git-push Documentation," reviewed
  2026-05-20. https://git-scm.com/docs/git-push
- [SPEC CITED: technical_doc] GitHub Docs, "Viewing workflow run history,"
  reviewed 2026-05-20.
  https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/viewing-workflow-run-history
- [SPEC CITED: technical_doc] GitHub Docs, "Events that trigger workflows:
  workflow_run," reviewed 2026-05-21.
  https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- [SPEC CITED: technical_doc] GitHub Docs, "REST API endpoints for workflow
  jobs," reviewed 2026-05-21.
  https://docs.github.com/en/rest/actions/workflow-jobs
- [SPEC CITED: technical_doc] GitHub Docs, "Using GitHub CLI in workflows,"
  reviewed 2026-05-21.
  https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-github-cli
- [SPEC CITED: technical_doc] GitHub Docs, "Workflow runs REST API,"
  reviewed 2026-05-21.
  https://docs.github.com/en/rest/actions/workflow-runs

## Test Plan

- `python .githooks/test__hook_helpers.py`
- `python scripts/test_precommit_docker.py`
- `python .githooks/test_prepare_commit_msg.py`
- `python -m pytest -q .githooks/test_check_gh_actions_read.py`
- `python -m pytest -q tests/test_agent_chat_format.py`
- `docker compose exec -T backend python -m pytest -p randomly -q --reuse-db apps/auto_issues/tests/test_drain_findings_buffer.py`
- `docker compose exec -T backend python -m pytest -p randomly -q --reuse-db --nomigrations apps/auto_issues/tests/test_file_ci_failure.py`
- `docker compose exec -T backend python -m pytest -p randomly -q --reuse-db --nomigrations apps/auto_issues/tests/test_print_failed_github_actions.py apps/auto_issues/tests/test_rotate_gh_actions_log.py`

[SPEC CITED: feature=fr-hook-finding-autoissue kind=technical_doc id=https://git-scm.com/docs/githooks verified_at=2026-06-02]
