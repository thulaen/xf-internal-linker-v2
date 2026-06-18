#!/usr/bin/env bash
# Dry-run entry point for KUBE PLAN Slices 26 and 27.
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --help) echo "Usage: $0 --dry-run"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ "$DRY_RUN" -ne 1 ]; then
  echo "Refusing to create distributed Jobs in rehearsal. Re-run with --dry-run." >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
"$HERE/lib/route-to-coordinator.sh"
python "$HERE/distributed_test_coordinator.py" --dry-run --run-id dry-run
