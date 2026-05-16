#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path go)"
evidence_container="$(quality_evidence_container_path go)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT

set +e
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
go_paths="$(python scripts/commit_scope.py paths --mode "$scope_mode" | grep -E '(^|/)go\.(mod|sum)$|\.go$' || true)"
if [[ -z "$go_paths" ]]; then
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type normal_test \
    --status passed \
    --tool-name go-quality \
    --command "bash scripts/run-go-quality.sh" \
    --summary "No changed Go file needed scoped Go quality checks." \
    --failure-fingerprint "go-quality:no-changed-targets" \
    --target-percent 95 \
    --actual-percent 100
  status_code=0
else
  docker compose run --rm -T \
    -e QUALITY_GO_PATHS="$go_paths" \
    compiled-tools sh -lc 'python /repo/scripts/check_go_tools.py --paths $QUALITY_GO_PATHS'
  status_code=$?
fi
set -e
status=failed
actual=0
if [[ "$status_code" -eq 0 ]]; then
  status=passed
  actual=100
fi
quality_evidence_write \
  --out "$evidence_file" \
  --check-type normal_test \
  --status "$status" \
  --tool-name go-quality \
  --command "docker compose run --rm -T compiled-tools python /repo/scripts/check_go_tools.py" \
  --summary "Go quality check ${status}." \
  --failure-fingerprint "go-quality:${status}" \
  --target-percent 95 \
  --actual-percent "$actual"
exit "$status_code"
