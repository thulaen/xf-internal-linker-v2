#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path quality-debt)"
evidence_container="$(quality_evidence_container_path quality-debt)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT

if [[ "${1:-}" == "--changed" ]]; then
  # Tool-scope contract: at pre-commit time the gate evaluates ONLY
  # the staged set, not the full worktree-dirty set. Untracked or
  # unstaged file changes are someone else's commit, not ours.
  staged="$(git diff --cached --name-only --diff-filter=ACM)"
  if [[ -z "$staged" ]]; then
    echo "No staged files for quality-debt scoring."
    exit 0
  fi
  staged_args=()
  while IFS= read -r path; do
    [[ -n "$path" ]] && staged_args+=("$path")
  done <<< "$staged"
  docker compose run --rm -T --no-deps \
    -e QUALITY_DEBT_PATHS="${staged_args[*]}" \
    backend sh -lc '
    set -eu
    cd /repo
    # shellcheck disable=SC2086
    python scripts/quality_debt_score.py \
      --paths $QUALITY_DEBT_PATHS \
      --baseline .quality-debt-baseline.json \
      --evidence-out backend/reports/quality-evidence/quality-debt.jsonl
  '
  exit 0
fi

docker compose run --rm -T --no-deps frontend-mutation-tools sh -lc '
  set -eu
  evidence=/repo/backend/reports/quality-evidence/quality-debt.jsonl
  npm run test:ci -- --code-coverage=true
  test -f coverage/xf-internal-linker-frontend/coverage-summary.json
  python3 /repo/scripts/check_quality_report.py \
    --kind angular-coverage \
    --metric lines \
    --target 95 \
    --report coverage/xf-internal-linker-frontend/coverage-summary.json \
    --rerun "npm run test:ci -- --code-coverage=true" \
    --evidence-out "$evidence" \
    --debt-only
  python3 /repo/scripts/check_quality_report.py \
    --kind angular-coverage \
    --metric branches \
    --target 85 \
    --report coverage/xf-internal-linker-frontend/coverage-summary.json \
    --rerun "npm run test:ci -- --code-coverage=true" \
    --evidence-out "$evidence" \
    --debt-only
  if test "${QUALITY_DEBT_RUN_FULL_MUTATION:-0}" = "1"; then
    npx stryker run || true
    if test -f reports/stryker.json; then
      python3 /repo/scripts/check_quality_report.py \
        --kind mutation \
        --tool stryker \
        --target 95 \
        --report reports/stryker.json \
        --rerun "npx stryker run" \
        --evidence-out "$evidence" \
        --debt-only
    else
      python3 /repo/scripts/write_quality_evidence.py \
        --out "$evidence" \
        --check-type missing_report \
        --status failed \
        --tool-name stryker \
        --command "npx stryker run" \
        --summary "Global Angular mutation debt report failed because Stryker did not create reports/stryker.json." \
        --failure-fingerprint "stryker:global-report-missing"
    fi
  else
    python3 /repo/scripts/write_quality_evidence.py \
      --out "$evidence" \
      --check-type mutation \
      --status failed \
      --tool-name stryker \
      --command "QUALITY_DEBT_RUN_FULL_MUTATION=1 bash scripts/run-quality-debt-report.sh" \
      --summary "Global Angular mutation testing is tracked as quality debt and is disabled unless QUALITY_DEBT_RUN_FULL_MUTATION=1 is set." \
      --failure-fingerprint "stryker:global-debt-deferred" \
      --target-percent 95 \
      --actual-percent 0
  fi
'
