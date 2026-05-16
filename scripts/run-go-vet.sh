#!/usr/bin/env bash
# Slice 1.5 — Go vet stage.
#
# Runs `go vet ./...` against every Go module touched by the scoped commit.
# Catches common Go bugs (printf format strings, lock-by-value, unreachable
# code) that the compiler ignores.
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed go vet."
  exit 0
fi

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  echo "+ go vet ./... in $module"
  if ! (cd "$module" && go vet ./...); then
    status=1
  fi
done <<<"$modules"

exit "$status"
