#!/usr/bin/env bash
# Rehearsal-safe restore helper for KUBE PLAN Slice 13.
set -euo pipefail

BACKUP_FILE=""
TARGET_DATABASE_URL="${TARGET_DATABASE_URL:-}"
EXECUTE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup) BACKUP_FILE="${2:-}"; shift 2 ;;
    --dry-run) EXECUTE=0; shift ;;
    --execute) EXECUTE=1; shift ;;
    --help)
      echo "Usage: TARGET_DATABASE_URL=... $0 --backup <dump> [--dry-run|--execute]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

echo "[DB RESTORE REHEARSAL]"
echo "Backup file: ${BACKUP_FILE:-missing --backup}"
echo "Target: ${TARGET_DATABASE_URL:-missing TARGET_DATABASE_URL}"

[ -n "$BACKUP_FILE" ] || { echo "--backup is required." >&2; exit 2; }
[ -f "$BACKUP_FILE" ] || { echo "Backup file not found: $BACKUP_FILE" >&2; exit 2; }

if [ "$EXECUTE" -ne 1 ]; then
  echo "Dry run only. Add --execute to run pg_restore."
  exit 0
fi

[ -n "$TARGET_DATABASE_URL" ] || { echo "TARGET_DATABASE_URL is required." >&2; exit 2; }
pg_restore --clean --if-exists --no-owner --dbname="$TARGET_DATABASE_URL" "$BACKUP_FILE"
echo "Restore complete into rehearsal target."
