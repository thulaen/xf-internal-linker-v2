# Layered Data-Loss Prevention

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

The app must keep the admin login, AutoIssue rows, PaperTrail rows, and database backups from being lost during agent work. The first fix path is to recreate the admin user when the user table is empty. The long-term fix is layered protection: command guards, database triggers, frequent snapshots, and plain debug commands.

This spec is the source of truth for the data-loss prevention work started on 2026-05-21.

## Sources

- PostgreSQL `CREATE TRIGGER` documentation, PostgreSQL 16: database triggers can reject unsafe deletes and truncates before the data changes.
- PostgreSQL `pg_dump` documentation, PostgreSQL 17: backups can be written as compressed archives and restored later.
- PostgreSQL setting documentation, PostgreSQL 18: `current_setting()` and session-local settings can be used for a one-transaction override.
- Docker `docker compose down` documentation: `--volumes` removes named volumes declared in the Compose file.
- Docker `docker volume rm` documentation: Docker can remove named volumes directly.
- Django custom management command documentation: recovery and inspection work that needs Django settings should be implemented as `manage.py` commands.
- Django migration operations documentation: `RunSQL` is the Django-supported way to install database-side SQL objects such as triggers.

## Protected Data

The protected Docker volume list is read from `config/protected-data-stores.json`. The list is not copied into code. At the time this spec was written, the current plan expects 25 protected volume names.

The protected database rows and tables are:

- `auth_user.username = "admin"`
- `auto_issues_autoissue`
- `paper_trail_papertrailentry`

## Required Behavior

### Admin Recovery

Given the user table is empty.
When `python manage.py ensure_admin --confirm` runs with `ADMIN_USERNAME` and `ADMIN_PASSWORD` set.
Then one superuser is created and an audit record is appended.

Given the user table already has any row.
When `python manage.py ensure_admin --confirm` runs.
Then it refuses to overwrite users and creates nothing.

Given the admin password setting is empty.
When the command runs.
Then it refuses and explains that the password must come from the environment.

### Command Guards

Given an agent tries `docker compose down -v`.
When the Claude command guard checks it.
Then the command is blocked unless it starts with `XF_DESTRUCTIVE_OP_APPROVED=1`.

Given a staged script contains `docker volume rm pgdata`.
When the pre-commit guard checks staged files.
Then the commit is stopped with a plain-English message.

Given malformed hook input reaches the Claude guard.
When the guard cannot parse the input.
Then it allows the command because lower protection layers still exist.

### Database Triggers

Given the admin row exists.
When SQL tries to delete that row.
Then PostgreSQL rejects the delete unless the current transaction sets `xf.allow_admin_delete = true`.

Given AutoIssue or PaperTrail tables exist.
When SQL tries to truncate either table.
Then PostgreSQL rejects the truncate unless the current transaction sets `xf.allow_bulk_delete = true`.

### Snapshot Cadence

Given the latest frequent snapshot is older than 15 minutes.
When the prompt hook runs.
Then it requests a fresh frequent backup and never blocks the user prompt if backup fails.

Given a new backup has the same database checksum as the latest backup in the same folder.
When the backup helper runs.
Then it updates the existing backup timestamp and does not write a duplicate dump.

Given a snapshot folder exceeds its byte cap.
When eviction runs.
Then the oldest unprotected snapshot files are removed until the folder is under the cap.

### Debug Commands

Given AutoIssue or PaperTrail tables are empty.
When the debug command runs.
Then it still prints valid human-readable output and valid JSON output.

Given the command succeeds.
When a future agent reads the output.
Then a stable marker line is present for search and handoff use.

## Design Notes

The layers are independent. The command guards stop common destructive commands before they run. The database triggers protect the most important data even if a command guard is bypassed. Backups reduce data loss if the disk or volume is still damaged. Debug commands let the next agent see state quickly without guessing.

The only override for destructive shell commands is the in-band prefix `XF_DESTRUCTIVE_OP_APPROVED=1`. This keeps each override tied to a single command. The database override is transaction-local and must include an audit reason through `allow_data_op`.

## Test Requirements

Tests must be written before or alongside code. The minimum focused suites are:

- `apps/core/tests_ensure_admin.py`
- `.claude/hooks/test_block_destructive_commands.py`
- `.githooks/test_check_no_destructive_docker_commands.py`
- `apps/core/tests_data_protection_triggers.py`
- `apps/core/tests_backups.py`
- `apps/core/tests_allow_data_op.py`
- `apps/auto_issues/tests_debug_autoissue.py`
- `apps/paper_trail/tests_debug_paper_trail.py`

Coverage target for new Python code is the repo default. The Rust FindBugs detector target remains stricter: 100% line coverage, 100% branch coverage, and no surviving mutation tests.

[SPEC CITED: feature=fr-layered-data-loss-prevention kind=technical_doc id=https://www.postgresql.org/docs/current/continuous-archiving.html verified_at=2026-06-02]
