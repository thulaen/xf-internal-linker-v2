#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-mutation
report_dir=/repo/backend/extensions/reports/mull

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir" "$report_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir" "$report_dir"
cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$build_dir" --parallel 2 --target test_fieldrel
cd "$build_dir"
mull-runner-19 \
  --reporters Elements \
  --report-dir "$report_dir" \
  --report-name mutants.json \
  --mutation-score-threshold 100 \
  ./test_fieldrel
