#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Phase H: shared concurrency + 5-min cap + named-container cleanup
# helper. Per the local test resource policy: every quality tool runs
# sequentially, with a 5-min wall-clock cap, and the docker container
# is force-removed on EXIT/INT/TERM so orphans like the 1h17m Stryker
# run from 2026-05-17 can't recur.
. scripts/_quality_concurrency.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock stryker

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path angular)"
evidence_container="$(quality_evidence_container_path angular)"
quality_evidence_init "$evidence_file"
# Combine the evidence-finalise trap with the existing concurrency
# cleanup trap. Both must fire on EXIT.
_run_angular_quality_combined_cleanup() {
  local rc=$?
  quality_evidence_finalize "$rc" "$evidence_file" "$evidence_container"
  quality_cleanup
  return "$rc"
}
trap _run_angular_quality_combined_cleanup EXIT
trap '_run_angular_quality_combined_cleanup; exit 130' INT
trap '_run_angular_quality_combined_cleanup; exit 143' TERM

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
changed_files="$(python scripts/commit_scope.py paths --mode "$scope_mode")"
new_files="$(python scripts/commit_scope.py new --mode "$scope_mode")"
frontend_lint_targets="$(
  printf "%s\n" "$changed_files" |
    grep -E '^frontend/src/app/.*\.(ts|html)$' |
    sed 's#^frontend/##' || true
)"
frontend_scss_targets="$(
  printf "%s\n" "$changed_files" |
    grep -E '^frontend/src/app/.*\.scss$' |
    sed 's#^frontend/##' || true
)"
frontend_test_includes="$(
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    rel="${path#frontend/}"
    if [[ "$rel" == *.spec.ts ]]; then
      printf "%s\n" "$rel"
      continue
    fi
    case "$rel" in
      src/app/*.component.ts|src/app/*.service.ts|src/app/*.directive.ts|src/app/*.pipe.ts)
        spec="${rel%.ts}.spec.ts"
        [[ -f "frontend/$spec" ]] && printf "%s\n" "$spec"
        ;;
      src/app/*.component.html|src/app/*.component.scss)
        spec="${rel%.component.*}.component.spec.ts"
        [[ -f "frontend/$spec" ]] && printf "%s\n" "$spec"
        ;;
    esac
  done <<< "$changed_files" | sort -u
)"

# Phase H: name the container so the cleanup trap can find it; register
# it with the helper so EXIT/INT/TERM force-remove it. The 5-min cap is
# enforced on each long-running step INSIDE the container by the
# script body (npm run test:ci, stryker run, etc.); the outer
# `docker compose run` itself runs uncapped because docker propagates
# SIGTERM into the container and the trap forces removal anyway.
QUALITY_CONTAINER="$(quality_docker_container_name stryker)"
quality_register_container "$QUALITY_CONTAINER"
docker compose run --rm -T --no-deps --name "$QUALITY_CONTAINER" \
  -e QUALITY_CHANGED_FILES="$changed_files" \
  -e QUALITY_NEW_FILES="$new_files" \
  -e QUALITY_FRONTEND_LINT_TARGETS="$frontend_lint_targets" \
  -e QUALITY_FRONTEND_SCSS_TARGETS="$frontend_scss_targets" \
  -e QUALITY_FRONTEND_TEST_INCLUDES="$frontend_test_includes" \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e XF_QUALITY_CORES="$(quality_cores)" \
  frontend-mutation-tools sh -lc '
  set -eu
  # 2026-05-17 — cd into /repo/frontend (the host-mounted source) instead
  # of the container default /app (image-built, becomes stale the moment
  # any frontend file is edited on the host). Before this fix, npm test
  # ran against the OLD source baked into the image and gave misleading
  # coverage numbers that ratcheted against the wrong file content.
  cd /repo/frontend
  # Helper functions for in-container 5-min caps; if XF_QUALITY_ENV=ci
  # the wrapper just runs the command without timeout.
  in_cap() {
    if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then "$@"; return $?; fi
    timeout --signal=TERM --kill-after=30 300 "$@"
  }
  evidence=/repo/backend/reports/quality-evidence/angular.jsonl
  if test -n "${QUALITY_FRONTEND_LINT_TARGETS:-}"; then
    in_cap npx eslint $QUALITY_FRONTEND_LINT_TARGETS
  else
    echo "No changed Angular TypeScript or template file needed ESLint."
  fi
  if test -n "${QUALITY_FRONTEND_SCSS_TARGETS:-}"; then
    in_cap npx stylelint $QUALITY_FRONTEND_SCSS_TARGETS
  else
    echo "No changed Angular stylesheet needed Stylelint."
  fi
  if test -n "${QUALITY_FRONTEND_TEST_INCLUDES:-}"; then
    in_cap npm run test:ci -- --code-coverage=true --include $QUALITY_FRONTEND_TEST_INCLUDES
    test -f coverage/xf-internal-linker-frontend/coverage-summary.json
    python3 /repo/scripts/check_quality_report.py \
      --kind angular-coverage \
      --metric lines \
      --target 95 \
      --report coverage/xf-internal-linker-frontend/coverage-summary.json \
      --rerun "npm run test:ci -- --code-coverage=true --include $QUALITY_FRONTEND_TEST_INCLUDES" \
      --evidence-out "$evidence" \
      --debt-only
    python3 /repo/scripts/check_quality_report.py \
      --kind angular-coverage \
      --metric branches \
      --target 85 \
      --report coverage/xf-internal-linker-frontend/coverage-summary.json \
      --rerun "npm run test:ci -- --code-coverage=true --include $QUALITY_FRONTEND_TEST_INCLUDES" \
      --evidence-out "$evidence" \
      --debt-only
    python3 /repo/scripts/check_quality_policy.py \
      angular-coverage \
      --report coverage/xf-internal-linker-frontend/coverage-summary.json \
      --evidence-out "$evidence"
  else
    python3 /repo/scripts/write_quality_evidence.py \
      --out "$evidence" \
      --check-type normal_test \
      --status passed \
      --tool-name karma \
      --command "npm run test:ci -- --include changed frontend specs" \
      --summary "No changed Angular file had a matching focused spec target." \
      --failure-fingerprint "karma:no-focused-changed-targets"
  fi
  mutation_targets="$(python3 /repo/scripts/check_quality_policy.py angular-targets)"
  if test -z "$mutation_targets"; then
    python3 /repo/scripts/write_quality_evidence.py \
      --out "$evidence" \
      --check-type mutation \
      --status passed \
      --tool-name stryker \
      --command "npx stryker run changed Angular targets" \
      --summary "No changed Angular component or service needed Stryker mutation testing." \
      --failure-fingerprint "stryker:no-changed-targets" \
      --target-percent 95 \
      --actual-percent 100
    exit 0
  fi
  python3 - "$mutation_targets" <<PY
import json
import sys
from pathlib import Path

targets = [line for line in sys.argv[1].splitlines() if line.strip()]
config = json.loads(Path("stryker.config.json").read_text(encoding="utf-8"))
config["mutate"] = targets
Path("/tmp/stryker.changed.config.json").write_text(
    json.dumps(config, indent=2, sort_keys=True),
    encoding="utf-8",
)
PY
  # Phase H: 5-min hard cap on Stryker. Phase I splits exit handling
  # so file_mutation_survivors (a Django command in the BACKEND
  # container) can run AFTER this frontend block exits. We capture
  # stryker_status here and write a sentinel file the outer host
  # script reads.
  set +e
  in_cap npx stryker run /tmp/stryker.changed.config.json
  stryker_status=$?
  set -e
  echo "$stryker_status" > reports/stryker-exit-status.txt
  if [ "${XF_QUALITY_ENV:-local}" = "ci" ] && [ "$stryker_status" -ne 0 ]; then
    exit "$stryker_status"
  fi
  test -f reports/stryker.json
  python3 /repo/scripts/check_quality_report.py \
    --kind mutation \
    --tool stryker \
    --target 95 \
    --report reports/stryker.json \
    --rerun "npx stryker run /tmp/stryker.changed.config.json" \
    --evidence-out "$evidence"
'

# Phase I: file surviving Stryker mutants as AutoIssues via the backend
# container. Local commits use mutation as a soft-block; the AutoIssues
# feed the 30-pick session quota and the C++ priority algorithm sorts
# them so dangerous mutants surface first. CI runs the same step but
# the upstream Stryker hard-block (check-mutation-score.py) already
# returned non-zero on regression.
if [ -f frontend/reports/stryker.json ]; then
  QUALITY_FILE_MUTANTS_CONTAINER="$(quality_docker_container_name file-mutants-stryker)"
  quality_register_container "$QUALITY_FILE_MUTANTS_CONTAINER"
  docker compose run --rm -T --no-deps --name "$QUALITY_FILE_MUTANTS_CONTAINER" \
    -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
    backend sh -lc '
    cd /repo/backend
    python manage.py file_mutation_survivors \
      --tool stryker \
      --report /repo/frontend/reports/stryker.json \
      --agent claude
  ' || echo "WARN: file_mutation_survivors stryker step failed (non-blocking)"
fi
