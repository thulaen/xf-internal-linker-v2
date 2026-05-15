#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh

bash scripts/run-tool-readiness.sh

staged="$(git diff --cached --name-only --diff-filter=ACM || true)"
if [[ -z "$staged" ]]; then
  echo "No staged files found."
  exit 0
fi

docker compose run --rm -T --no-deps backend sh -lc '
  cd /repo
  python .githooks/check-glossary.py $(git diff --cached --name-only --diff-filter=ACM)
  python scripts/verify_deep_links.py
'

if grep -E '^frontend/.*\.(ts|html|scss)$' <<<"$staged" >/dev/null; then
  bash scripts/run-angular-quality.sh
fi

if grep -E '^backend/.*\.py$' <<<"$staged" >/dev/null; then
  bash scripts/run-python-quality.sh
fi

if grep -E '^backend/extensions/.*\.(cpp|h)$' <<<"$staged" >/dev/null; then
  bash scripts/run-cpp-quality.sh
fi

if grep -E '(^|/)go\.(mod|sum)$|\.go$' <<<"$staged" >/dev/null; then
  bash scripts/run-go-quality.sh
fi

bash scripts/run-quality-debt-report.sh --changed
quality_artifact_safe_prune_host
