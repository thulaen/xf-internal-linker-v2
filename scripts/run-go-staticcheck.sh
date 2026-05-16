#!/usr/bin/env bash
# Slice 1.5 — Go staticcheck stage.
#
# Runs `staticcheck ./...` against every Go module touched by the scoped
# commit. Strictest of the Go static-analysis tools (catches dead code,
# misuse of standard library, suspicious nil checks, etc.).
#
# Honours services/<name>/staticcheck.conf for narrowly silenced findings.
# Each silenced finding must carry an inline comment explaining the reason.
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed staticcheck."
  exit 0
fi

if ! command -v staticcheck >/dev/null 2>&1; then
  echo "staticcheck not installed in this image — skipping (slice 1.5 step 26 adds it)."
  exit 0
fi

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  echo "+ staticcheck ./... in $module"
  if ! (cd "$module" && staticcheck ./...); then
    status=1
  fi
done <<<"$modules"

exit "$status"
