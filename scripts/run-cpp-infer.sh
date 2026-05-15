#!/usr/bin/env bash
# Facebook Infer static-analysis step for the C++ extension surface.
#
# Scope contract (per the tool-scope table in the agent rules):
#   Infer covers semantic defects clang-tidy/cppcheck/iwyu cannot —
#   null derefs, uninitialised reads, resource leaks, dead stores,
#   taint flow. It does NOT replace clang-format / clang-tidy /
#   cppcheck / iwyu (style + correctness diagnostics) or Mull
#   (mutation testing) or ASan/UBSan (runtime sanitizers).
#
# Run inside the `compiled-tools` Docker container where Infer is
# installed (see `tools/mutation/Dockerfile`, INFER_VERSION=1.2.0).
#
# Usage:
#   bash scripts/run-cpp-infer.sh             # incremental
#   bash scripts/run-cpp-infer.sh --clean     # wipe + rebuild
set -euo pipefail

build_dir=/tmp/xf-build/cpp-infer
report_dir=/repo/backend/extensions/reports/infer

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir" "$report_dir"
fi

cd /repo/backend/extensions
mkdir -p "$build_dir" "$report_dir"

cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON >/dev/null

# Use the compilation database so Infer mirrors the real build invocations
# instead of guessing flags. Capture is the per-file analysis pass.
infer capture \
  --results-dir "$report_dir" \
  --compilation-database "$build_dir/compile_commands.json"

# Analyze produces the JSON report. `--fail-on-issue` flips Infer's
# exit code to non-zero when any defect is reported.
#
# Scope: production C++ source under `backend/extensions/` plus the
# public headers under `include/`. Test files (`tests/`), benchmarks
# (`benchmarks/`), fuzz harnesses (`fuzz/`), and third-party fetched
# deps (CMake's `_deps/`) are skipped — those areas are covered by
# clang-tidy, GoogleTest, libFuzzer, and upstream maintainers
# respectively, per the tool-scope contract.
infer analyze \
  --results-dir "$report_dir" \
  --skip-analysis-in-path "_deps/" \
  --skip-analysis-in-path "tests/" \
  --skip-analysis-in-path "benchmarks/" \
  --skip-analysis-in-path "fuzz/" \
  --fail-on-issue

# Convenience copy at a stable path so write_quality_evidence.py can
# read the report without knowing Infer's internal layout.
cp "$report_dir/report.json" "$report_dir/report.copy.json"

echo "infer: report at $report_dir/report.json"
