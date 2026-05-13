#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-fuzz

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions/fuzz
mkdir -p "$build_dir"
cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$build_dir" --parallel 2

for target in fuzz_simsearch fuzz_scoring fuzz_passagesim fuzz_quantemb fuzz_rareterm fuzz_texttok; do
  echo "Running ${target}..."
  "$build_dir/$target" -runs=0
done
