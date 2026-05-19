#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
. scripts/_quality_concurrency.sh
quality_install_cleanup_trap

bash scripts/run-tool-readiness.sh

staged="$(python scripts/commit_scope.py paths --mode staged || true)"
if [[ -z "$staged" ]]; then
  echo "No staged files found."
  exit 0
fi

printf "%s\n" "$staged" | xargs python .githooks/check-glossary.py

quality_docker_compose_run precommit-deep-links backend \
  -e COMMIT_SCOPE_PATHS="$staged" \
  sh -lc '
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
#
# 2026-05-18 — re-wire the TDD-pipeline hooks that were temporarily reverted
# during Commit A's chain-debugging. The chain MUST enforce the pipeline so
# agents cannot ship new production code without strict TDD evidence. See
# AutoIssue #295 (CRITICAL: chain revert dropped TDD-pipeline enforcement).
run_hard_gate python .githooks/check-tdd-preflight.py
run_hard_gate python .githooks/check-decision-point.py
run_hard_gate python .githooks/check-session-close.py
run_hard_gate python .githooks/check-tdd-strict.py
run_hard_gate python .githooks/check-test-case-mandate.py
run_hard_gate python .githooks/check-lessons-read-at-session-start.py
run_hard_gate python .githooks/check-snapshotd-ritual.py
run_hard_gate python .githooks/check-code-review-lessons.py
# 2026-05-18 — Per-file search_resolved_issues hard mandate. Refuses any
# commit whose staged production source files lack a disk-backed audit
# entry in audit/resolved_issues_lookup_log.jsonl under the current task.
run_hard_gate python .githooks/check-resolved-history.py
# 2026-05-18 user directive — commit-failure lookup. Refuses any commit that
# has no audit log entry in audit/commit_failures_lookup_log.jsonl under the
# current task_id. Run `manage.py search_commit_failures` once per task.
run_hard_gate python .githooks/check-commit-failures-lookup.py
run_hard_gate python .githooks/check-registry-read.py
run_hard_gate python .githooks/check-paper-trail-read.py
run_hard_gate python .githooks/check-paper-trail-evidence.py
run_hard_gate python .githooks/check-deferral-filed.py
run_hard_gate python .githooks/check-profiling-proof.py
run_hard_gate python .githooks/check-perf-proof.py
run_hard_gate python .githooks/check-tdd-cycle.py
run_hard_gate python .githooks/check-spec-citation.py
run_hard_gate python .githooks/check-scoped-lessons.py
run_hard_gate python .githooks/check-debug-code.py
run_hard_gate python .githooks/check-junk-files.py
# Slice 1.5 — Go services tier boundary + contract enforcement.
run_hard_gate python .githooks/check-no-cross-language-import.py
run_hard_gate python .githooks/check-go-service-contract.py
# Rules J + L (2026-05-16) — C++ kernel lifecycle invariant + stubs only
# move when the contract moves. Both fire only when relevant paths are in
# the staged diff so they cost nothing on unrelated commits.
run_hard_gate python .githooks/check-cpp-lifecycle.py
run_hard_gate python .githooks/check-stubs-not-regenerated.py

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
