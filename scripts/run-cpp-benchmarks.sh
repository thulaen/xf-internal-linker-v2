#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-benches

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions/benchmarks
mkdir -p "$build_dir"
cmake -B "$build_dir" -S . -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 2

find "$build_dir" -maxdepth 1 -type f -name 'bench_*' -executable -print0 |
  sort -z |
  while IFS= read -r -d '' bench; do
    name=${bench##*/}
    echo "Running ${name}..."
    "$bench"
  done
