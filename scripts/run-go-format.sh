#!/usr/bin/env bash
# Slice 1.5 — Go format stage.
#
# Runs `gofmt -l` against every Go module touched by the scoped commit. Any
# file flagged by gofmt fails the stage. Hard-block at commit because
# misformatted code defeats the diff hygiene the rest of the chain assumes.
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed gofmt."
  exit 0
fi

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  echo "+ gofmt -l   $module"
  flagged=$(cd "$module" && gofmt -l .)
  if [[ -n "$flagged" ]]; then
    echo "Go files need gofmt in $module:"
    echo "$flagged"
    status=1
  fi
done <<<"$modules"

exit "$status"
