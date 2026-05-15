#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-static

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
find . \( -name "*.cpp" -o -name "*.h" \) \
  -not -path "*/build/*" \
  -not -path "*/build_*/*" \
  -not -path "*/_deps/*" \
  -print0 | xargs -0 clang-format-19 --dry-run --Werror --style=file

cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

mapfile -t sources < <(find . -maxdepth 1 -name "*.cpp" | sort)
if [[ "${#sources[@]}" -eq 0 ]]; then
  echo "FAIL: no C++ source files found for static analysis."
  exit 1
fi

clang-tidy-19 --quiet -p "$build_dir" "${sources[@]}"
cppcheck --enable=warning,performance,portability --std=c++17 \
  --error-exitcode=1 --suppress=missingIncludeSystem "${sources[@]}"
iwyu_tool -p "$build_dir" "${sources[@]}" -- -Xiwyu --error
