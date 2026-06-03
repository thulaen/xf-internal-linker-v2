#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/_quality_concurrency.sh"

build_dir=/tmp/xf-build/cpp-tests

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions

# Enable distributed compilation when Mint's icecc daemon is reachable.
# Falls back silently to local-only if icecc is not installed or
# ICECC_SCHEDULER is unset.  Spec: docs/specs/fr-icecc-distributed-cpp.md
. /repo/scripts/icecc_helper.sh

mkdir -p "$build_dir"
mapfile -t targets < <(python /repo/scripts/cpp_mutation_targets.py | grep -v '^#' || true)
if [[ "${#targets[@]}" -eq 0 ]]; then
  quality_log_scope_skip "scripts/run-cpp-tests.sh" ctest 10
  echo "No changed C++ test binary needed GoogleTest."
  exit 0
fi
target_regex="$(IFS='|'; echo "^(${targets[*]})$")"
# shellcheck disable=SC2086  # ICECC_CMAKE_LAUNCHER_FLAGS intentionally word-splits
cmake -B "$build_dir" -S . -DCMAKE_BUILD_TYPE=Release $ICECC_CMAKE_LAUNCHER_FLAGS
cmake --build "$build_dir" --parallel "$ICECC_JOBS" --target "${targets[@]}"
cd "$build_dir"
ctest -R "$target_regex" --output-on-failure --schedule-random -j "$ICECC_JOBS"
