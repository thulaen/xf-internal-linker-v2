#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh

bash scripts/run-tool-readiness.sh
docker compose config >/dev/null
bash scripts/run-python-quality.sh
bash scripts/run-angular-quality.sh
bash scripts/run-cpp-quality.sh
bash scripts/run-go-quality.sh
bash scripts/run-quality-debt-report.sh --changed
git diff --check
quality_artifact_safe_prune_host
