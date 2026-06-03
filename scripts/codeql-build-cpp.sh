#!/usr/bin/env bash
set -euo pipefail

build_dir="${CODEQL_CPP_BUILD_DIR:-tmp/codeql/build/cpp}"
jobs="${CODEQL_BUILD_JOBS:-2}"

cmake -S backend/extensions -B "$build_dir" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$build_dir" --parallel "$jobs"
