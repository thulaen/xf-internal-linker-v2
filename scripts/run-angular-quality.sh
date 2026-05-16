#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path angular)"
evidence_container="$(quality_evidence_container_path angular)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
changed_files="$(python scripts/commit_scope.py paths --mode "$scope_mode")"
new_files="$(python scripts/commit_scope.py new --mode "$scope_mode")"

docker compose run --rm -T --no-deps \
  -e QUALITY_CHANGED_FILES="$changed_files" \
  -e QUALITY_NEW_FILES="$new_files" \
  frontend-mutation-tools sh -lc '
  set -eu
  evidence=/repo/backend/reports/quality-evidence/angular.jsonl
  npm run lint
  npm run lint:scss
  npm audit --audit-level=high
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
  python3 /repo/scripts/check_quality_policy.py \
    angular-coverage \
    --report coverage/xf-internal-linker-frontend/coverage-summary.json \
    --evidence-out "$evidence"
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
  npx stryker run /tmp/stryker.changed.config.json
  test -f reports/stryker.json
  python3 /repo/scripts/check_quality_report.py \
    --kind mutation \
    --tool stryker \
    --target 95 \
    --report reports/stryker.json \
    --rerun "npx stryker run /tmp/stryker.changed.config.json" \
    --evidence-out "$evidence"
'
