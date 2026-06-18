#!/usr/bin/env bash
# Rehearsal-safe MSI database backup helper for KUBE PLAN Slice 13.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups/kube-migration}"
SOURCE_DATABASE_URL="${SOURCE_DATABASE_URL:-}"
EXECUTE=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) EXECUTE=0 ;;
    --execute) EXECUTE=1 ;;
    --help)
      echo "Usage: SOURCE_DATABASE_URL=... $0 [--dry-run|--execute]"
      exit 0
      ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$BACKUP_DIR/msi-postgres-$timestamp.dump"

echo "[DB BACKUP REHEARSAL]"
echo "Backup path: $backup_path"
echo "Source: ${SOURCE_DATABASE_URL:-missing SOURCE_DATABASE_URL}"

if [ "$EXECUTE" -ne 1 ]; then
  echo "Dry run only. Add --execute to run pg_dump."
  exit 0
fi

[ -n "$SOURCE_DATABASE_URL" ] || { echo "SOURCE_DATABASE_URL is required." >&2; exit 2; }
mkdir -p "$BACKUP_DIR"
pg_dump "$SOURCE_DATABASE_URL" --format=custom --file="$backup_path"
sha256sum "$backup_path" > "$backup_path.sha256"
echo "Backup complete: $backup_path"
