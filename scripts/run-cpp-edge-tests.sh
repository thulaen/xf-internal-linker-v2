#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-edge-tests

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions/benchmarks
mkdir -p "$build_dir"
cmake -B "$build_dir" -S . -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 2 --target test_edges_simsearch test_edges_scoring
"$build_dir/test_edges_simsearch" --gtest_shuffle
"$build_dir/test_edges_scoring" --gtest_shuffle
