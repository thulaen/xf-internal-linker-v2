#!/usr/bin/env bash
# Slice 1.5 — buf lint stage.
#
# Runs `buf lint` against every services/<name>/api.proto contract touched by
# the scoped commit. buf enforces protobuf style and detects breaking changes
# (catalogued in buf.build/docs/lint/rules). Each Go service that publishes a
# .proto contract gets linted here.
#
# Skipped when no .proto contract exists in scope (e.g. services that publish
# api.http.md instead).
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed buf lint."
  exit 0
fi

if ! command -v buf >/dev/null 2>&1; then
  echo "buf not installed in this image — skipping (slice 1.5 step 26 adds it)."
  exit 0
fi

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  proto="$module/api.proto"
  if [[ ! -f "$proto" ]]; then
    echo "No api.proto in $module — skipping buf lint (HTTP+JSON contracts are out of scope here)."
    continue
  fi
  echo "+ buf lint $proto"
  if ! (cd "$module" && buf lint api.proto); then
    status=1
  fi
done <<<"$modules"

exit "$status"
