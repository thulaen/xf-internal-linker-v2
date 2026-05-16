#!/usr/bin/env bash
# Slice 1.5 — Go benchmark stage.
#
# Runs `go test -bench=. -benchmem -count=1 -run=^$ ./...` against every Go
# module touched by the scoped commit that has any `bench_*_test.go` or
# `*_bench_test.go` files. The stage is a no-op when no benchmark files are
# in scope — keeps pre-commit fast.
#
# Output captured to backend/reports/go-quality/<stem>.bench.txt so the
# quality_debt_score can parse trends over time.
set -euo pipefail

repo_root="${REPO_ROOT:-/repo}"
modules=$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS)
if [[ -z "$modules" ]]; then
  echo "No scoped Go module needed benchmarks."
  exit 0
fi

report_root="$repo_root/backend/reports/go-quality"
mkdir -p "$report_root"

status=0
while IFS= read -r module; do
  [[ -z "$module" ]] && continue
  if ! find "$module" -type f \( -name 'bench_*_test.go' -o -name '*_bench_test.go' \) -print -quit | grep -q .; then
    echo "No bench files in $module — skipping."
    continue
  fi
  stem=$(python -c "import hashlib,sys;p=sys.argv[1];print(p.replace('/','__').replace('.','_').lstrip('_') + '-' + hashlib.sha256(p.encode()).hexdigest()[:12])" "$module")
  bench_path="$report_root/$stem.bench.txt"
  echo "+ go test -bench=. -benchmem -count=1 -run='^$' ./... in $module"
  if (cd "$module" && go test -bench=. -benchmem -count=1 -run='^$' ./...) | tee "$bench_path"; then
    echo "Benchmark output written to $bench_path"
  else
    status=1
  fi
done <<<"$modules"

exit "$status"
