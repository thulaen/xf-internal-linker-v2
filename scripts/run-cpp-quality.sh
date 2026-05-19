#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Phase H: shared concurrency + 5-min cap + named-container cleanup.
. scripts/_quality_concurrency.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock cpp-quality

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path cpp)"
evidence_container="$(quality_evidence_container_path cpp)"
quality_evidence_init "$evidence_file"
_run_cpp_quality_combined_cleanup() {
  local rc=$?
  quality_evidence_finalize "$rc" "$evidence_file" "$evidence_container"
  quality_cleanup
  return "$rc"
}
trap _run_cpp_quality_combined_cleanup EXIT
trap '_run_cpp_quality_combined_cleanup; exit 130' INT
trap '_run_cpp_quality_combined_cleanup; exit 143' TERM

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
  # Phase H: 5-min cap on every C++ step. Each step's docker container
  # gets a stable name so the cleanup trap can force-remove it on
  # signal. Mull (mutation) honours the same cap.
  local container_name
  container_name="$(quality_docker_container_name "cpp-$tool_name")"
  # Rewrite the command to inject --name and force-remove any stale
  # container first. Append --name flag to the docker compose run.
  local prefixed_command
  prefixed_command="docker rm -f $container_name >/dev/null 2>&1 || true; ${command/docker compose run/docker compose run --name $container_name}"
  quality_register_container "$container_name"
  quality_timeout 300 bash -c "$prefixed_command"
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

# Phase I: file surviving Mull mutants per binary. Mull writes one
# report per binary under backend/extensions/reports/mull/<binary>/
# mutants.json. Soft-block locally; CI's check-mutation-score keeps the
# original hard test.
mull_report_root="backend/extensions/reports/mull"
if [ -d "$mull_report_root" ]; then
  for binary_dir in "$mull_report_root"/*/; do
    [ -d "$binary_dir" ] || continue
    binary=$(basename "$binary_dir")
    report="$binary_dir/mutants.json"
    [ -f "$report" ] || continue
    QUALITY_FILE_MUTANTS_CONTAINER="$(quality_docker_container_name "file-mutants-mull-$binary")"
    quality_register_container "$QUALITY_FILE_MUTANTS_CONTAINER"
    docker compose run --rm -T --no-deps --name "$QUALITY_FILE_MUTANTS_CONTAINER" \
      -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
      backend sh -lc "
      cd /repo/backend
      python manage.py file_mutation_survivors \
        --tool mull \
        --report /repo/$report \
        --agent claude
    " || echo "WARN: file_mutation_survivors mull/$binary step failed (non-blocking)"
  done
fi
