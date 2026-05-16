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

# Paper-trail ritual gate — validates the [PAPER TRAIL READ: ...] marker
# in the staged AGENT-HANDOFF.md and (for code-changing commits) calls
# manage.py verify_paper_trail_quota to prove the 10 picks are resolved.
python .githooks/check-paper-trail-read.py

# Every-deferral-filed gate (added 2026-05-16) — scans the staged
# AGENT-HANDOFF.md added lines for deferral verbs and requires a matching
# `[PAPER TRAIL FILED: #<N>]` marker for each. Hard-block on shortfall.
python .githooks/check-deferral-filed.py

# Rule A — 20× speedup gate. Hard-blocks code-changing commits that
# lack a [PERFORMANCE PROOF] or [PERFORMANCE EXEMPTION] marker.
python .githooks/check-perf-proof.py

# Rule B — Strict Red-Green-Refactor TDD. Hard-blocks code-changing
# commits that lack a [TDD CYCLE] marker.
python .githooks/check-tdd-cycle.py

# Rule C — Spec citations. Hard-blocks new docs/specs/*.md files that
# lack a [SPEC CITED] marker.
python .githooks/check-spec-citation.py

# Rule D — Scoped lesson reading. Hard-blocks code-changing commits
# that lack a [SCOPED LESSONS READ: N lessons in ...] marker.
python .githooks/check-scoped-lessons.py

# Rule G — Code-review lessons logged to AutoIssue. Hard-blocks code-
# changing commits without a [CODE REVIEW LESSONS: N logged from M
# files; deduped K against prior] marker.
python .githooks/check-code-review-lessons.py

# ── Rule H sub-rules (file-scoped) ───────────────────────────────
# H.H1 — block debug code in production paths
python .githooks/check-debug-code.py

# H.H2 — reject local secret / junk files
python .githooks/check-junk-files.py

# H.H4 — block mutable default arguments (ruff B006 delegate)
if grep -E '^backend/.*\.py$|^scripts/.*\.py$' <<<"$staged" >/dev/null; then
  python .githooks/check-mutable-defaults.py
fi

# H.H10 — Django deploy-safety check (only on settings / asgi / wsgi / urls)
if grep -E '^backend/config/(settings/|asgi\.py|wsgi\.py|urls\.py)' <<<"$staged" >/dev/null; then
  python .githooks/check-django-deploy.py
fi

# H.H22 — explicit on_delete on every Django FK
if grep -E '^backend/apps/.*/models\.py$' <<<"$staged" >/dev/null; then
  python .githooks/check-fk-on-delete.py
fi

# H.H25 — management commands must support --dry-run
if grep -E '^backend/apps/.*/management/commands/.*\.py$' <<<"$staged" >/dev/null; then
  python .githooks/check-mgmt-command-dry-run.py
fi

quality_artifact_safe_prune_host
