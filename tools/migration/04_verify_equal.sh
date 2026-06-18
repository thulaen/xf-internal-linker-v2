#!/usr/bin/env bash
# Compare source and rehearsal database row-count files.
set -euo pipefail

SOURCE_COUNTS=""
TARGET_COUNTS=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-counts) SOURCE_COUNTS="${2:-}"; shift 2 ;;
    --target-counts|--counts-file) TARGET_COUNTS="${2:-}"; shift 2 ;;
    --help)
      echo "Usage: $0 --source-counts <file> --target-counts <file>"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$SOURCE_COUNTS" ] || { echo "--source-counts is required." >&2; exit 2; }
[ -n "$TARGET_COUNTS" ] || { echo "--target-counts is required." >&2; exit 2; }
[ -f "$SOURCE_COUNTS" ] || { echo "Missing source counts: $SOURCE_COUNTS" >&2; exit 2; }
[ -f "$TARGET_COUNTS" ] || { echo "Missing target counts: $TARGET_COUNTS" >&2; exit 2; }

source_sorted="$(mktemp)"
target_sorted="$(mktemp)"
trap 'rm -f "$source_sorted" "$target_sorted"' EXIT

sort "$SOURCE_COUNTS" > "$source_sorted"
sort "$TARGET_COUNTS" > "$target_sorted"

if diff -u "$source_sorted" "$target_sorted"; then
  echo "[DB ROW COUNT PROOF: matched]"
  exit 0
fi

echo "[DB ROW COUNT PROOF: mismatch]" >&2
exit 1
