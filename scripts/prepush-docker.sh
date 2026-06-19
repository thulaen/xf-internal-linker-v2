#!/usr/bin/env bash
# Push-time mutation gate — Bazel is the public entry point.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

export COMMIT_SCOPE_PATHS="${COMMIT_SCOPE_PATHS:-$(python scripts/commit_scope.py paths --mode push || true)}"
command_text="$(printf "%q " python scripts/bazel_default.py run //tools/quality:mutation -- "$@")"

affected_bazel_targets="$(python scripts/bazel_affected_targets.py --changed --mode push || true)"
if ! grep -Fx '//tools/quality:mutation' <<<"$affected_bazel_targets" >/dev/null; then
  echo "SKIP prepush-mutation: no changed files map to the Bazel mutation target." >&2
  exit 0
fi

if python scripts/quality_cache.py check-gate \
  --tool gate:prepush-mutation \
  --paths-env COMMIT_SCOPE_PATHS \
  --command-text "$command_text" >/dev/null 2>&1; then
  echo "SKIP prepush-mutation: passed previously for the current changed-file scope." >&2
  exit 0
fi

set +e
python scripts/bazel_default.py run //tools/quality:mutation -- "$@"
code=$?
set -e

if [[ "$code" -eq 0 ]]; then
  python scripts/quality_cache.py record-gate \
    --tool gate:prepush-mutation \
    --paths-env COMMIT_SCOPE_PATHS \
    --command-text "$command_text" >/dev/null 2>&1 || true
fi
exit "$code"
