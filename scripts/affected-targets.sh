#!/usr/bin/env bash
# Print existing Bazel targets touched by the current Git diff or given paths.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/scripts/affected_targets.py" "$@"
