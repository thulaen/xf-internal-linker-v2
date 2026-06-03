#!/usr/bin/env bash
set -euo pipefail

jobs="${CODEQL_BUILD_JOBS:-2}"
export GOMAXPROCS="$jobs"

while IFS= read -r module; do
  dir="$(dirname "$module")"
  (cd "$dir" && go test -run '^$' ./...)
done < <(git ls-files 'services/**/go.mod')
