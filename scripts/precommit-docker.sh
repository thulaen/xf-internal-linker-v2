#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh

bash scripts/run-tool-readiness.sh

staged="$(python scripts/commit_scope.py paths --mode staged || true)"
if [[ -z "$staged" ]]; then
  echo "No staged files found."
  exit 0
fi

printf "%s\n" "$staged" | xargs python .githooks/check-glossary.py

docker compose run --rm -T --no-deps \
  -e COMMIT_SCOPE_PATHS="$staged" \
  backend sh -lc '
  cd /repo
  python scripts/verify_deep_links.py --paths-env COMMIT_SCOPE_PATHS
'

hard_gate_status=0
run_hard_gate() {
  if ! "$@"; then
    hard_gate_status=1
  fi
}

# Run hard gates before slower language checks and collect every failure.
# This keeps AutoIssue, Paper Trail, code review, and proof gates from
# being hidden by an earlier failed test command.
run_hard_gate python .githooks/check-code-review-lessons.py
run_hard_gate python .githooks/check-registry-read.py
run_hard_gate python .githooks/check-paper-trail-read.py
run_hard_gate python .githooks/check-deferral-filed.py
run_hard_gate python .githooks/check-profiling-proof.py
run_hard_gate python .githooks/check-perf-proof.py
run_hard_gate python .githooks/check-tdd-cycle.py
run_hard_gate python .githooks/check-spec-citation.py
run_hard_gate python .githooks/check-scoped-lessons.py
run_hard_gate python .githooks/check-debug-code.py
run_hard_gate python .githooks/check-junk-files.py

if grep -E '^backend/.*\.py$|^scripts/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate python .githooks/check-mutable-defaults.py
fi

if grep -E '^backend/config/(settings/|asgi\.py|wsgi\.py|urls\.py)' <<<"$staged" >/dev/null; then
  run_hard_gate python .githooks/check-django-deploy.py
fi

if grep -E '^backend/apps/.*/models\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate python .githooks/check-fk-on-delete.py
fi

if grep -E '^backend/apps/.*/management/commands/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate python .githooks/check-mgmt-command-dry-run.py
fi

if [[ "$hard_gate_status" -ne 0 ]]; then
  exit "$hard_gate_status"
fi

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
