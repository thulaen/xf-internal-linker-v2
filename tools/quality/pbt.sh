#!/usr/bin/env bash
set -euo pipefail
repo_root="${REPO_ROOT:-${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}}"
cd "$repo_root"
exec bash scripts/run-pbt.sh "$@"
