#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-sanitizers

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
mapfile -t targets < <(python /repo/scripts/cpp_mutation_targets.py | grep -v '^#' || true)
if [[ "${#targets[@]}" -eq 0 ]]; then
  echo "No changed C++ test binary needed sanitizer run."
  exit 0
fi
target_regex="$(IFS='|'; echo "^(${targets[*]})$")"
cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined"
cmake --build "$build_dir" --parallel 2 --target "${targets[@]}"
ctest --test-dir "$build_dir" -R "$target_regex" --output-on-failure --schedule-random -j 2
