#!/usr/bin/env bash
set -euo pipefail

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

# Keep this list in sync with XF_GTEST_TARGETS in
# backend/extensions/CMakeLists.txt.
targets=(
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

cmake --build "$build_dir" --parallel 2 --target "${targets[@]}"

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
  if mull-runner-19 \
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
