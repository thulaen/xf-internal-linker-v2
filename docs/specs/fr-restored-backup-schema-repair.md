# Restored Backup Schema Repair

[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]

[SPEC CITED: feature=restored-backup-schema-repair kind=technical_doc id=https://docs.djangoproject.com/en/dev/topics/migrations/ verified_at=2026-05-19T04:58:00Z]
[SPEC CITED: feature=restored-backup-schema-repair kind=technical_doc id=https://www.postgresql.org/docs/current/static/information-schema.html verified_at=2026-05-19T04:58:00Z]
[SPEC CITED: feature=restored-backup-schema-repair kind=technical_doc id=https://docs.djangoproject.com/en/3.2/howto/custom-management-commands/ verified_at=2026-05-19T04:58:00Z]

## Goal

A restored older database backup may already contain tables or columns that match today's code while its `django_migrations` history is stale. The repair command must make that state safe without deleting rows or faking unproven schema.

## Required Behavior

Given a restored backup has the required May 18 table shape but is missing matching migration records, when `manage.py repair_restored_backup_schema` runs, then it records only those proven migration records and leaves all application rows untouched.

Given a restored backup is missing required columns or indexes, when the repair command runs in check mode, then it fails with a plain-English message and does not record migration history.

Given a restored backup needs only normal Django migrations, when the repair command runs before `manage.py migrate`, then it does not fake those migrations and tells the operator to run the normal migration command.

## Scope

The first version covers the two stale-restore surfaces found after the May 14 backup restore:

- `auto_issues` migrations `0011` through `0013`.
- `paper_trail` migrations `0001` through `0004`.

The command may write only to Django's migration-history table. It must not delete or update application data rows.

## Verification

- Dry run reports repairable migration records without writing them.
- Check mode fails while repairable drift exists.
- Default mode records only verified migration rows.
- A final check passes when schema shape and migration history agree.
