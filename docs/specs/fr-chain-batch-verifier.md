# Chain Batch Verifier

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Commit checks currently repeat the same expensive pattern: start a Docker
command, check one database row or one quota, then repeat. This spec defines one
backend command, `verify_chain_batch`, that checks many commit-proof records in
one backend process and returns one JSON result.

## User Outcome

Given a commit has many test-driven-development lessons, test cases,
code-review lessons, work-queue picks, paper-trail picks, and paper-trail
evidence rows.
When the hooks run their database checks.
Then they call one batch verifier per hook and keep the same pass or fail
decisions they had before, while spending less time starting Docker.

## Requirements

1. The command name is `verify_chain_batch`.
2. The command accepts comma-separated ID lists for:
   - `--tdd-lessons`
   - `--test-cases`
   - `--code-review-lessons`
   - `--autoissue-quota`
   - `--paper-trail-quota`
   - `--paper-trail-evidence`
3. The command accepts `--resolved-after` for the two quota checks.
4. The command accepts `--health` and returns a JSON health report without
   spawning subprocesses.
5. With `--json`, stdout is JSON. Each requested group maps string IDs to a
   result object: `{"status": "pass"}` or `{"status": "fail", "reason": "..."}`.
6. Batch checks must preserve the existing rules:
   - TDD lesson rows must be AutoIssues with category `tdd_lesson`, status
     `resolved`, and `Trap:` plus `Fix shape:` in `lessons_learned`.
   - Test-case rows must be AutoIssues with category `test_case` and
     Given/When/Then text in `lessons_learned`.
   - Code-review lesson rows must be AutoIssues with category
     `code_review_lesson` and status `resolved`.
   - AutoIssue quota rows must be exactly 30 unique resolved rows, have
     `resolved_at`, have lessons, respect the cutoff when supplied, and avoid
     duplicate canonical fingerprints.
   - Paper-trail quota rows must be exactly 10 unique resolved rows, have
     `resolved_at`, have `Trap:` plus `Fix shape:` in `resolution_lessons`,
     respect the cutoff when supplied, and avoid duplicate canonical
     fingerprints.
   - Paper-trail evidence rows must match the same evidence rule enforced by
     `verify_paper_trail_evidence`.
7. The AutoIssue row groups must use batched database reads with
   `AutoIssue.objects.filter(id__in=...).values(...)` or an equivalent
   single-query shape per group.
8. The command must not call subprocesses. Hook scripts own Docker process
   startup; the backend command owns database validation.
9. Hook JSON parsing must live in `.githooks/_hook_helpers.py` so the six hooks
   do not duplicate parser and error handling code.

## Behavior Scenarios

Given AutoIssues #1, #2, and #3 are valid TDD lesson rows, and #4 has the wrong
category.
When `verify_chain_batch --tdd-lessons 1,2,3,4 --json` runs.
Then rows #1, #2, and #3 pass, and row #4 fails with a wrong-category reason.

Given 50 IDs are split across all supported groups.
When one `verify_chain_batch --json` command runs.
Then each group is checked with bounded database reads, no subprocess is
spawned inside the command, and the test fixture completes in under one second.

Given the database is reachable and Django has no app-check error.
When `verify_chain_batch --health --json` runs.
Then it exits 0 and reports `postgres`, `backend`, `auto_issues_table`,
`helper_failure_rate_per_hour`, and `buffer_unflushed_count`.

Given the database connection fails.
When `verify_chain_batch --health --json` runs.
Then it exits non-zero and reports the database failure in JSON.

## Design Notes

The batch verifier is Python because the slow part being removed is Docker
process startup, not row validation compute. The command performs bounded
database queries and returns JSON. It is not a ranking or import hot path and
does not need a C++ extension.

At 10x and 100x the expected input still stays bounded by commit-marker count.
The command deduplicates IDs before querying so repeated markers do not add
extra database work.

## Acceptance Checks

- Focused backend tests for the batch command and service pass.
- Focused hook tests prove the old per-ID verifier commands are not called.
- A search for old command forms in `.githooks/` returns no active production
  hits for the consolidated commands.
- Existing failure behavior is preserved: a bad row still stops the commit.

## Citations

- Django Software Foundation, QuerySet API reference, `filter`, `values`, and
  `select_related`, official Django documentation:
  https://docs.djangoproject.com/en/stable/ref/models/querysets/
- Django Software Foundation, custom management commands, official Django
  documentation:
  https://docs.djangoproject.com/en/stable/howto/custom-management-commands/
- Python Software Foundation, `json` module, official Python documentation:
  https://docs.python.org/3/library/json.html
- Python Software Foundation, `argparse` module, official Python documentation:
  https://docs.python.org/3/library/argparse.html
- PostgreSQL Global Development Group, `SELECT` command documentation,
  official PostgreSQL documentation:
  https://www.postgresql.org/docs/current/sql-select.html

[SPEC CITED: feature=fr-chain-batch-verifier kind=technical_doc id=https://docs.djangoproject.com/en/stable/ref/models/querysets/ verified_at=2026-06-02]
