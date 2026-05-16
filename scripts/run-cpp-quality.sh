#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path cpp)"
evidence_container="$(quality_evidence_container_path cpp)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
cpp_files="$(python scripts/commit_scope.py paths --mode "$scope_mode" | grep -E '^backend/extensions/.*\.(cpp|h)$' || true)"
if [[ -z "$cpp_files" ]]; then
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type normal_test \
    --status passed \
    --tool-name cpp-quality \
    --command "bash scripts/run-cpp-quality.sh" \
    --summary "No changed C++ file needed scoped C++ quality checks." \
    --failure-fingerprint "cpp-quality:no-changed-targets"
  exit 0
fi
export QUALITY_CPP_CHANGED_FILES="$cpp_files"

run_cpp_step() {
  local check_type="$1"
  local tool_name="$2"
  local command="$3"
  set +e
  eval "$command"
  local status_code=$?
  set -e
  local status=failed
  local actual=0
  if [[ "$status_code" -eq 0 ]]; then
    status=passed
    actual=100
  fi
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type "$check_type" \
    --status "$status" \
    --tool-name "$tool_name" \
    --command "$command" \
    --summary "C++ ${tool_name} check ${status}." \
    --failure-fingerprint "cpp:${tool_name}:${status}" \
    --target-percent 100 \
    --actual-percent "$actual"
  return "$status_code"
}

run_cpp_step static_analysis cpp-static "docker compose run --rm -T -e QUALITY_CPP_CHANGED_FILES compiled-tools bash /repo/scripts/run-cpp-static.sh --clean"
run_cpp_step static_analysis cpp-infer "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-infer.sh --clean"
run_cpp_step normal_test cpp-tests "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-tests.sh --clean"
run_cpp_step coverage cpp-coverage "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-coverage.sh --clean"
run_cpp_step fuzz cpp-fuzz "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-fuzz-smoke.sh --clean"
run_cpp_step sanitizer cpp-sanitizers "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-sanitizers.sh --clean"
run_cpp_step mutation mull "docker compose run --rm -T compiled-tools bash /repo/scripts/run-cpp-mutation.sh --clean"
