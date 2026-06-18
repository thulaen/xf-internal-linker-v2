# KUBE PLAN Slice 13 Rollback Notes

This file records the rollback path for the rehearsed database migration.

Rollback remains available until the operator gives an explicit go-live signal.
The rehearsal pass does not repoint the live app, so the default rollback is:

1. Keep the MSI database running.
2. Keep the latest `tools/migration/01_backup_msi.sh` dump and its `.sha256`
   file.
3. If a rehearsal restore fails, drop only the rehearsal target database.
4. Re-run restore from the saved dump.
5. Re-run `tools/migration/04_verify_equal.sh` with source and target row-count
   files.

Live rollback during go-live must include:

1. Restore app settings to the previous MSI database host.
2. Restart backend and worker pods.
3. Check admin login and row counts again.
4. Leave the Dell restored database untouched until a manual review confirms it
   can be deleted or retained for investigation.
