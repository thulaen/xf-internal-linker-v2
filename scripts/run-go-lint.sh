#!/usr/bin/env bash
# Slice 1.5 — Go golangci-lint stage.
#
# Runs `golangci-lint run ./...` against every Go module touched by the scoped
# commit. Meta-linter that bundles many Go linters into one pass. Honours
# services/<name>/.golangci.yml when present so per-service strictness can be
# tuned without forking the global config.
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed golangci-lint."
  exit 0
fi

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  echo "+ golangci-lint run ./... in $module"
  if ! (cd "$module" && golangci-lint run ./...); then
    status=1
  fi
done <<<"$modules"

exit "$status"
