# audit/ — disk-backed enforcement for the per-file `search_resolved_issues` mandate

This directory is the durable source of truth for the 2026-05-18 user rule:

> Before modifying any file, the agent (Claude, Codex, Gemini) MUST run
> `search_resolved_issues` for that exact file path. The lookup is required
> once per file before the first modification to that file in the current
> agent task. If a new task starts, the lookup must be run again.

The pre-commit chain enforces the rule by reading the files in this directory.

## Files (all git-tracked)

### `resolved_issues_index.jsonl`

One JSON object per line. The disk-backed snapshot of every resolved
`AutoIssue` row, exploded by `affected_files` so each entry is keyed by ONE
file path. The Postgres `pgdata` volume is the primary store; this JSONL
file is the survivability snapshot that survives any `docker compose down -v`,
backup-restore, or pgdata wipe.

Schema (all fields are required unless marked optional; empty string is allowed
for unknown values):

```
{
  "file_path":                "backend/apps/auto_issues/services/fingerprinting.py",
  "issue_title":              "canonical_fingerprint dedup bug (AutoIssue #260)",
  "date_resolved":            "2026-05-18T18:59:01Z",
  "root_cause":               "<plain-English one-liner>",
  "what_failed":              "<symptom an agent would observe>",
  "what_fixed_it":            "<concrete change that resolved the symptom>",
  "regression_risk":          "<what could break if the fix is reverted or rewritten>",
  "tests_added_or_changed":   ["<repo-relative test paths>"],
  "related_files":            ["<repo-relative paths touched alongside this fix>"],
  "patterns_to_avoid":        ["<short one-liners; what NOT to do>"],
  "safe_implementation_notes":"<concrete guidance for the next edit>",
  "autoissue_id":             270,
  "source":                   "AutoIssue:#270",
  "category":                 "tdd_lesson",
  "concept_tags":             ["canonical-fingerprint", "tdd-cycle-strict"]
}
```

Regenerate with `manage.py export_resolved_issues_index`.

### `resolved_issues_lookup_log.jsonl`

Append-only audit log. Every successful `manage.py search_resolved_issues`
invocation appends one row per `--area <path>` argument.

Schema:

```
{
  "file_path":  "backend/apps/auto_issues/services/fingerprinting.py",
  "lookup_at":  "2026-05-18T22:30:14Z",
  "task_id":    "51e2f5c6-7853-4549-94e2-79c260f0c12a",
  "agent":      "claude",
  "result_count": 1,
  "result_ids": [270]
}
```

The pre-commit hook `.githooks/check-resolved-history.py` reads this log and
refuses the commit when any staged production source file has no matching
audit entry for the current task.

## RAM cache rule

A RAM cache may be used by `search_resolved_issues` for speed, but the cache
MUST be populated from `resolved_issues_index.jsonl` at session start or on
first lookup. A memory-only lookup is NOT acceptable evidence; the audit log
entry must still be written to disk for the hook to count it.

## Task identifier

`task_id` is the UUID printed in the `[TDD PREFLIGHT: ... session_id=<uuid>
armed_at=... ]` marker of the current session's AGENT-HANDOFF.md entry. One
task = one preflight invocation. If preflight has not been run for the
session, the task_id falls back to the SHA of `(git HEAD + current day in
ISO 8601 UTC)` so the audit log is still keyed deterministically.
