#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-tests

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
cmake -B "$build_dir" -S . -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 2
cd "$build_dir"
ctest --output-on-failure --schedule-random -j 2
