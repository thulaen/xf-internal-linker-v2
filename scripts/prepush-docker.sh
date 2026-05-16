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
export COMMIT_SCOPE_MODE="${COMMIT_SCOPE_MODE:-push}"
scoped_paths="$(python scripts/commit_scope.py paths --mode "$COMMIT_SCOPE_MODE" || true)"
if [[ -z "$scoped_paths" ]]; then
  echo "No scoped files found for pre-push quality checks."
  exit 0
fi
if grep -E '^backend/.*\.py$' <<<"$scoped_paths" >/dev/null; then
  bash scripts/run-python-quality.sh
fi
if grep -E '^frontend/.*\.(ts|html|scss)$' <<<"$scoped_paths" >/dev/null; then
  bash scripts/run-angular-quality.sh
fi
if grep -E '^backend/extensions/.*\.(cpp|h)$' <<<"$scoped_paths" >/dev/null; then
  bash scripts/run-cpp-quality.sh
fi
if grep -E '(^|/)go\.(mod|sum)$|\.go$' <<<"$scoped_paths" >/dev/null; then
  bash scripts/run-go-quality.sh
fi
bash scripts/run-quality-debt-report.sh --changed
git diff --check
quality_artifact_safe_prune_host
