#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

echo "Bazel is the required quality path. Routing frontend quality through //tools/quality:frontend." >&2
exec python scripts/bazel_default.py run //tools/quality:frontend -- "$@"
