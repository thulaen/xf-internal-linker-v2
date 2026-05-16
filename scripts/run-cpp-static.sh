#!/usr/bin/env bash
set -euo pipefail

build_dir=/tmp/xf-build/cpp-static

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
if [[ -n "${QUALITY_CPP_CHANGED_FILES:-}" ]]; then
  mapfile -t format_files < <(
    printf "%s\n" "$QUALITY_CPP_CHANGED_FILES" |
      sed "s#^backend/extensions/##" |
      grep -E '\.(cpp|h)$' || true
  )
else
  mapfile -t format_files < <(
    find . \( -name "*.cpp" -o -name "*.h" \) \
      -not -path "*/build/*" \
      -not -path "*/build_*/*" \
      -not -path "*/_deps/*" |
      sed "s#^\./##"
  )
fi
if [[ "${#format_files[@]}" -gt 0 ]]; then
  clang-format-19 --dry-run --Werror --style=file "${format_files[@]}"
fi

cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

if [[ -n "${QUALITY_CPP_CHANGED_FILES:-}" ]]; then
  mapfile -t sources < <(
    printf "%s\n" "$QUALITY_CPP_CHANGED_FILES" |
      sed "s#^backend/extensions/##" |
      grep -E '^[^/]+\.cpp$' |
      sort || true
  )
else
  mapfile -t sources < <(find . -maxdepth 1 -name "*.cpp" | sed "s#^\./##" | sort)
fi
if [[ "${#sources[@]}" -eq 0 ]]; then
  echo "No changed C++ source files needed clang-tidy, cppcheck, or include-what-you-use."
  exit 0
fi

clang-tidy-19 --quiet -p "$build_dir" "${sources[@]}"
cppcheck --enable=warning,performance,portability --std=c++17 \
  --error-exitcode=1 --suppress=missingIncludeSystem "${sources[@]}"
iwyu_tool -p "$build_dir" "${sources[@]}" -- -Xiwyu --error
