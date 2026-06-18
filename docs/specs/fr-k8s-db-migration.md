# FR - Rehearsed Database Migration From MSI To Dell

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 13 creates the safe database migration path. In this pass it is rehearsal
only: the scripts can make backups, restore into a rehearsal database, compare
row counts, and print rollback steps, but they do not repoint the live app.

## Current Source Of Truth

- Backup script: `tools/migration/01_backup_msi.sh`.
- Baseline count query: `tools/migration/02_baseline_counts_msi.sql`.
- Restore script: `tools/migration/03_restore_dell.sh`.
- Count comparison script: `tools/migration/04_verify_equal.sh`.
- Guarded cutover script: `tools/migration/05_cutover.sh`.
- Rollback notes: `tools/migration/ROLLBACK.md`.

## Behavior

Given a backup file and a rehearsal target database, when the restore and count
scripts run, then the scripts fail if the backup is missing, fail if counts do
not match, and write a plain-English proof file for later go-live review.

## Rehearsal Boundary

The cutover script refuses to run unless `--execute` is provided with an explicit
proof file. The default action is a dry run.

## Citations

- PostgreSQL documentation - pg_dump: https://www.postgresql.org/docs/current/app-pgdump.html
- PostgreSQL documentation - pg_restore: https://www.postgresql.org/docs/current/app-pgrestore.html
- PostgreSQL documentation - COPY: https://www.postgresql.org/docs/current/sql-copy.html
