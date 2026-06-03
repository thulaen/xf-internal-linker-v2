#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/_quality_concurrency.sh"

build_dir=/tmp/xf-build/cpp-coverage
report_file="$build_dir/coverage.filtered.info"
report_dir=/repo/backend/reports/cpp-coverage

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir"
mkdir -p "$report_dir"
mapfile -t targets < <(python /repo/scripts/cpp_mutation_targets.py | grep -v '^#' || true)
if [[ "${#targets[@]}" -eq 0 ]]; then
  quality_log_scope_skip "scripts/run-cpp-coverage.sh" coverage 100
  echo "No changed C++ test binary needed coverage."
  exit 0
fi
target_regex="$(IFS='|'; echo "^(${targets[*]})$")"
cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=gcc \
  -DCMAKE_CXX_COMPILER=g++ \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCOVERAGE=ON
cmake --build "$build_dir" --parallel 2 --target "${targets[@]}"
ctest --test-dir "$build_dir" -R "$target_regex" --output-on-failure --schedule-random -j 2
lcov --capture --directory "$build_dir" --output-file "$build_dir/coverage.info" \
  --ignore-errors mismatch --rc lcov_branch_coverage=1
lcov --extract "$build_dir/coverage.info" "/repo/backend/extensions/*.cpp" \
  --ignore-errors unused --rc lcov_branch_coverage=1 \
  --output-file "$build_dir/coverage.source.info"
lcov --remove "$build_dir/coverage.source.info" "*/_deps/*" "*/tests/*" "*/build_*/*" \
  --ignore-errors unused --rc lcov_branch_coverage=1 \
  --output-file "$report_file"
lcov -a "$report_file" --filter branch \
  --output-file "$build_dir/coverage.branch-filtered.info" \
  --rc lcov_branch_coverage=1
report_file="$build_dir/coverage.branch-filtered.info"
# GCC emits synthetic exception edges as branch IDs beginning with "e".
# They are compiler plumbing, not source decisions, so the source gate removes
# them before enforcing the project branch target.
awk '!/^BRDA:[^,]*,e[0-9]+,/ && !/^BRF:/ && !/^BRH:/' "$report_file" \
  > "$build_dir/coverage.project-branches.info"
report_file="$build_dir/coverage.project-branches.info"
cp "$report_file" "$report_dir/coverage.filtered.info"
lcov --summary "$report_file" --rc lcov_branch_coverage=1 | tee "$build_dir/coverage-summary.txt"
cp "$build_dir/coverage-summary.txt" "$report_dir/coverage-summary.txt"
grep -q "branches.*100.0%" "$build_dir/coverage-summary.txt"
