#!/usr/bin/env bash
# Slice 1.5 — Go quality orchestrator.
#
# Replaces the thin wrapper that called scripts/check_go_tools.py with a
# stage-by-stage runner that mirrors scripts/run-cpp-quality.sh: one stage =
# one quality_evidence_write row.
#
# Stages, in order:
#   go-format         gofmt -l
#   go-vet            go vet ./...
#   staticcheck       staticcheck ./...
#   golangci          golangci-lint run ./...
#   gosec             gosec ./...
#   buf-lint          buf lint api.proto (skipped per service if absent)
#   go-tests          go test -race -shuffle=on -count=1 -coverprofile
#   go-mutesting      go-mutesting (kill-rate gate >= 70%)
#   go-bench          go test -bench=. -benchmem -count=1 -run='^$' (when bench files staged)
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
quality_acquire_tool_lock go-quality

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path go)"
evidence_container="$(quality_evidence_container_path go)"
quality_evidence_init "$evidence_file"
_run_go_quality_combined_cleanup() {
  local rc=$?
  quality_evidence_finalize "$rc" "$evidence_file" "$evidence_container"
  quality_cleanup
  return "$rc"
}
trap _run_go_quality_combined_cleanup EXIT
trap '_run_go_quality_combined_cleanup; exit 130' INT
trap '_run_go_quality_combined_cleanup; exit 143' TERM

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
go_paths="$(python scripts/commit_scope.py paths --mode "$scope_mode" | grep -E '(^|/)go\.(mod|sum)$|\.go$|\.proto$' || true)"
if [[ -z "$go_paths" ]]; then
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type normal_test \
    --status passed \
    --tool-name go-quality \
    --command "bash scripts/run-go-quality.sh" \
    --summary "No changed Go or proto file needed scoped Go quality checks." \
    --failure-fingerprint "go-quality:no-changed-targets"
  exit 0
fi
export QUALITY_GO_PATHS="$go_paths"

run_go_step() {
  local check_type="$1"
  local tool_name="$2"
  local command="$3"
  set +e
  # Phase H: 5-min cap on every Go step + stable container name so
  # cleanup trap can force-remove the docker container on signal.
  local container_name
  container_name="$(quality_docker_container_name "go-$tool_name")"
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
    --summary "Go ${tool_name} check ${status}." \
    --failure-fingerprint "go:${tool_name}:${status}" \
    --target-percent 100 \
    --actual-percent "$actual"
  return "$status_code"
}

run_go_step static_analysis go-format    "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-format.sh"
run_go_step static_analysis go-vet       "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-vet.sh"
run_go_step static_analysis staticcheck  "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-staticcheck.sh"
run_go_step static_analysis golangci     "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-lint.sh"
run_go_step static_analysis gosec        "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-gosec.sh"
run_go_step static_analysis buf-lint     "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-buf-lint.sh"
run_go_step coverage        go-tests     "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-tests.sh"
run_go_step mutation        go-mutesting "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-mutation.sh"

# Phase I: file surviving go-mutesting mutants per module. The script
# writes <module>/report.json. Soft-block locally; CI's score-ratchet
# keeps the original hard test.
go_modules_for_survivors="$(python "$repo_root/scripts/go_modules.py" --paths-env QUALITY_GO_PATHS 2>/dev/null || true)"
if [ -n "$go_modules_for_survivors" ]; then
  while IFS= read -r mod; do
    [ -z "$mod" ] && continue
    report="$mod/report.json"
    [ -f "$report" ] || continue
    mod_safe="${mod//\//-}"
    QUALITY_FILE_MUTANTS_CONTAINER="$(quality_docker_container_name "file-mutants-gomut-$mod_safe")"
    quality_register_container "$QUALITY_FILE_MUTANTS_CONTAINER"
    docker compose run --rm -T --no-deps --name "$QUALITY_FILE_MUTANTS_CONTAINER" \
      -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
      backend sh -lc "
      cd /repo/backend
      python manage.py file_mutation_survivors \
        --tool go-mutesting \
        --report /repo/$report \
        --agent claude
    " || echo "WARN: file_mutation_survivors go-mutesting/$mod step failed (non-blocking)"
  done <<<"$go_modules_for_survivors"
fi
run_go_step normal_test     go-bench     "docker compose run --rm -T -e QUALITY_GO_PATHS compiled-tools bash /repo/scripts/run-go-bench.sh"
