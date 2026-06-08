#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh

# Defense in depth: enforce the AutoIssue + paper-trail quotas at push too, so a
# commit that somehow skipped the pre-commit chain still cannot reach the remote
# without the quotas met. Must run before the quality/tool-readiness step.
python .githooks/check-autoissue-quota.py
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

if grep -E '^backend/apps/.*\.py$' <<<"$scoped_paths" > /dev/null; then
  python .githooks/check-scoped-mutation.py
fi

# \u2500\u2500 Mutation hard gates (pre-push) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# Mutation runs ONLY at pre-push, never at pre-commit.
# All three languages route 100% to Dell via mutation-routing.json.
# turbo_mutation.py returns 1 when the kill rate is below the configured
# gate (python=90%, typescript=70%, rust=75%) \u2014 this script treats that
# as a hard block: the push is rejected and git reports the failure to the
# developer. No mutation = no push.
_run_mutation_hard() {
  local lang="$1"
  local label="turbo-mutation-${lang}"
  local outfile
  outfile="$(mktemp "${TMPDIR:-/tmp}/xf-mutation-${lang}.XXXXXX")"
  set +e
  python scripts/turbo_mutation.py --language "$lang" 2>&1 | tee "$outfile"
  local code="${PIPESTATUS[0]}"
  set -e
  if [[ "$code" -ne 0 ]]; then
    printf "\nFAIL %s: turbo mutation hard-blocked the push (exit %s).\n" "$label" "$code" >&2
    printf "WHY: the %s kill-rate gate in config/mutation-routing.json was not met.\n" "$lang" >&2
    printf "UNBLOCK: add tests that kill the surviving mutants, then retry the push.\n" >&2
    rm -f "$outfile"
    exit "$code"
  fi
  rm -f "$outfile"
}

if grep -qE '^backend/.*\.py$' <<<"$scoped_paths"; then
  _run_mutation_hard python
fi
if grep -qE '\.rs$|Cargo\.(toml|lock)' <<<"$scoped_paths"; then
  _run_mutation_hard rust
fi
if grep -qE '^frontend/.*\.(ts|html|scss)$' <<<"$scoped_paths"; then
  _run_mutation_hard typescript
fi

git diff --check
quality_artifact_safe_prune_host
