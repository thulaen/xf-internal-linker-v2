#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-tests

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
mapfile -t targets < <(python /repo/scripts/cpp_mutation_targets.py | grep -v '^#' || true)
if [[ "${#targets[@]}" -eq 0 ]]; then
  echo "No changed C++ test binary needed GoogleTest."
  exit 0
fi
target_regex="$(IFS='|'; echo "^(${targets[*]})$")"
cmake -B "$build_dir" -S . -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 2 --target "${targets[@]}"
cd "$build_dir"
ctest -R "$target_regex" --output-on-failure --schedule-random -j 2
