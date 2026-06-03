#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Phase H: this script normally runs INSIDE the compiled-tools docker
# container (invoked from run-cpp-quality.sh). When the outer wrapper
# fires it, the concurrency helper has already locked + trapped. When
# the script is run directly on the host, fall through to the helper
# so it gets the same protections.
if [ -z "${XF_QUALITY_INSIDE_CONTAINER:-}" ] && [ -f /.dockerenv ]; then
  export XF_QUALITY_INSIDE_CONTAINER=1
fi
if [ -f "$script_dir/_quality_concurrency.sh" ]; then
  . "$script_dir/_quality_concurrency.sh"
fi
if [ -z "${XF_QUALITY_INSIDE_CONTAINER:-}" ]; then
  quality_install_cleanup_trap
  quality_acquire_meta_lock
  quality_acquire_tool_lock cpp-mutation
fi

# Phase H: in-container 5-min cap helper. Mull mutation runs on each
# binary are individually capped at 60s; the whole loop has a 5-min
# outer cap.
_cpp_in_cap() {
  if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then "$@"; return $?; fi
  if command -v timeout >/dev/null 2>&1; then
    timeout --signal=TERM --kill-after=10 "$@"
  else
    "$@"
  fi
}

# Run Mull mutation testing across every C++ GTest binary in
# backend/extensions/CMakeLists.txt's XF_GTEST_TARGETS set.
#
# Each binary gets its own report directory under
# backend/extensions/reports/mull/<binary>/mutants.json so the ratchet
# in .githooks/check-mutation-score.py can track per-target scores
# independently.
#
# Mull needs LLVM IR metadata embedded in the binaries. We enable the
# `MULL_BUILD` CMake option which adds
# `-fpass-plugin=/usr/lib/mull-ir-frontend-19 -O0 -g` via
# `add_compile_options(...)` in CMakeLists.txt so the include paths
# from `target_include_directories(...)` and FetchContent (gtest) are
# preserved. Without these flags mull-runner reported "No mutants
# found" and the gate passed vacuously for months.
#
# The script runs every binary even if an earlier one failed, so the
# operator sees the full picture in one run. Exit code is non-zero
# only after the full loop finishes when at least one binary failed.

build_dir=/tmp/xf-build/cpp-mutation
report_dir=/repo/backend/extensions/reports/mull
ir_frontend=/usr/lib/mull-ir-frontend-19

# K1 (Phase K): targets are file-scoped via scripts/cpp_mutation_targets.py
# which parses CMakeLists.txt and intersects with the staged C++ changes.
# No matching target means no-op, not "run every binary"; unrelated mutation
# runs caused long commit checks that hid the actual changed-file result.
all_targets=(
  test_fieldrel
  test_scoring
  test_passagesim
  test_simsearch
  test_quantemb
  test_ivf_index
  test_streaming_sketches
  test_papertrail_dedup
  test_lesson_index
)
targets=()
if [ -x "$(command -v python)" ] && [ -f "$(dirname "$0")/cpp_mutation_targets.py" ]; then
  scoped_output="$(python "$(dirname "$0")/cpp_mutation_targets.py" 2>/dev/null || true)"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in
      \#*) continue ;;  # comment line from the helper's stderr that leaked
    esac
    targets+=("$line")
  done <<<"$scoped_output"
fi
if [ "${#targets[@]}" -eq 0 ]; then
  quality_log_scope_skip "scripts/run-cpp-mutation.sh" mull 7
  echo "No changed C++ mutation target needed Mull mutation testing."
  exit 0
fi

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir" "$report_dir"
fi

if [[ ! -f "$ir_frontend" ]]; then
  echo "FAIL: Mull IR frontend pass plugin not found at $ir_frontend"
  echo "      Mutation testing cannot run without it (mull-runner-19"
  echo "      would report 'no mutants found' and pass vacuously)."
  exit 1
fi

cd /repo/backend/extensions
mkdir -p "$build_dir" "$report_dir"

cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DMULL_BUILD=ON \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

_cpp_in_cap 300 cmake --build "$build_dir" --target "${targets[@]}"

cd "$build_dir"

failed_targets=()
for target in "${targets[@]}"; do
  target_report_dir="$report_dir/$target"
  mkdir -p "$target_report_dir"

  echo ""
  echo "=== Mull mutation: $target ==="
  # No --mutation-score-threshold here; .githooks/check-mutation-score.py
  # is the ratchet (called per-binary in CI). mull-runner-19 itself just
  # needs to run cleanly and produce the report.
  # Phase H: 60s per-binary cap. Whole loop is bounded by the outer
  # script timeout (started from run-cpp-quality.sh with quality_timeout
  # 300) so the total budget stays 5 min even if every binary uses 60s.
  if _cpp_in_cap 60 mull-runner-19 \
      --reporters Elements \
      --report-dir "$target_report_dir" \
      --report-name mutants \
      "./$target"; then
    echo "=== $target: report generated ==="
  else
    echo "=== $target: RUN FAILED ==="
    failed_targets+=("$target")
  fi
done

if (( ${#failed_targets[@]} > 0 )); then
  echo ""
  echo "FAIL: Mull-runner crashed for: ${failed_targets[*]}"
  exit 1
fi

echo ""
echo "OK: Mull ran successfully on all ${#targets[@]} targets."
echo "    Per-binary ratchet enforcement happens via check-mutation-score.py."
