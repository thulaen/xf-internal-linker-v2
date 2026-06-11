#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
. scripts/_quality_concurrency.sh
. .githooks/findings-transcript.sh
quality_install_cleanup_trap

hooks_ran=0
findings_filed=0
hard_block_failures=0
findings_transcript="$(xf_findings_transcript_path)"

_print_precommit_summary() {
  printf "Pre-commit done. %s hooks ran, %s findings filed, %s hard-block failures.\n" \
    "${hooks_ran}" "${findings_filed}" "${hard_block_failures}"
}

_finish_precommit() {
  local code="$1"
  _print_precommit_summary
  exit "$code"
}

_reset_findings_transcript() {
  if [[ "${XF_QUALITY_ENV:-local}" == "ci" ]]; then
    rm -f "$findings_transcript"
    return 0
  fi
  : > "$findings_transcript"
}

_collect_finding_ids() {
  local output_file="$1"
  if [[ "${XF_QUALITY_ENV:-local}" == "ci" ]]; then
    return 0
  fi
  local finding_id
  while IFS= read -r finding_id; do
    if [[ -z "$finding_id" ]]; then
      continue
    fi
    printf "%s\n" "$finding_id" >> "$findings_transcript"
    findings_filed=$((findings_filed + 1))
  done < <(sed -nE 's/.*\[(HOOK )?FINDING FILED:[^]]*([Aa]uto[Ii]ssue|autoissue)=#?([0-9]+)[^]]*\].*/\3/p' "$output_file")
}

_first_failure_detail() {
  local output_file="$1"
  local detail
  detail="$(
    awk '/blocked:/ { sub(/^.*blocked:[[:space:]]*/, "staged "); print; exit }
         /FAIL/ { sub(/^.*FAIL[: ]*/, ""); print; exit }' "$output_file"
  )"
  if [[ -z "$detail" ]]; then
    detail="exit non-zero"
  fi
  printf "%s\n" "$detail"
}

_commit_blocker_reason() {
  local output_file="$1"
  local reason
  reason="$(
    awk '/^WHY:/ { sub(/^WHY:[[:space:]]*/, ""); print; exit }
         /blocked:/ { sub(/^.*blocked:[[:space:]]*/, ""); print; exit }
         /FAIL/ { sub(/^.*FAIL[: ]*/, ""); print; exit }' "$output_file"
  )"
  if [[ -z "$reason" ]]; then
    reason="the hook returned a non-zero result"
  fi
  printf "%s\n" "$reason"
}

_commit_blocker_unblock() {
  local output_file="$1"
  local unblock
  unblock="$(awk '/^UNBLOCK:/ { sub(/^UNBLOCK:[[:space:]]*/, ""); print; exit }' "$output_file")"
  if [[ -z "$unblock" ]]; then
    unblock="fix the hook failure named above, then retry the commit"
  fi
  printf "%s\n" "$unblock"
}

_commit_blocker_fingerprint() {
  python -c 'import hashlib, sys; print(hashlib.sha1(sys.stdin.buffer.read(), usedforsecurity=False).hexdigest()[:16])'
}

_commit_blocker_occurrence() {
  local issue_id="$1"
  docker compose exec -T backend python manage.py shell -c \
    "from apps.auto_issues.models import AutoIssue; print(AutoIssue.objects.get(pk=${issue_id}).occurrence_count)" \
    2>/dev/null | tail -n 1
}

_run_commit_blocker_filing() {
  local message="$1"
  local external_id="$2"
  local lessons="$3"
  docker compose exec -T backend python manage.py file_hook_finding \
    --category commit_blocker \
    --severity high \
    --subject "scripts/precommit-docker.sh:1" \
    --message "$message" \
    --agent codex \
    --external-id "$external_id" \
    --lessons-learned "$lessons" 2>&1
}

_file_commit_blocker() {
  local name="$1"
  local output_file="$2"
  local timestamp detail reason unblock full_output fingerprint external_id message lessons filing_output issue_id occurrence

  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  detail="$(_first_failure_detail "$output_file")"
  reason="$(_commit_blocker_reason "$output_file")"
  unblock="$(_commit_blocker_unblock "$output_file")"
  full_output="$(cat "$output_file")"
  fingerprint="$(printf "%s" "${name}:${detail}:${reason}:${unblock}" | _commit_blocker_fingerprint)"
  external_id="commit_blocker::${name}::${fingerprint}"
  message="${name} refused commit at ${timestamp}. ${name} blocked commit: ${detail}

Full hook output:
${full_output}

Trap: ${reason}
Fix shape: ${unblock}"
  lessons="Trap: ${reason}
Fix shape: ${unblock}"

  set +e
  filing_output="$(_run_commit_blocker_filing "$message" "$external_id" "$lessons")"
  local filing_code=$?
  set -e

  printf "%s\n" "$filing_output" >&2
  if [[ "$filing_code" -ne 0 ]]; then
    printf "unfiled\n"
    return 0
  fi

  issue_id="$(sed -nE 's/.*AutoIssue=#([0-9]+).*/\1/p' <<<"$filing_output" | tail -n 1)"
  if [[ -z "$issue_id" ]]; then
    printf "unfiled\n"
    return 0
  fi
  if grep -F "[HOOK FINDING DEDUPED:" <<<"$filing_output" >/dev/null; then
    occurrence="$(_commit_blocker_occurrence "$issue_id")"
    if [[ "$occurrence" =~ ^[0-9]+$ && "$occurrence" -gt 1 ]]; then
      printf "%s (%s time)\n" "$issue_id" "$occurrence"
      return 0
    fi
  fi
  printf "%s\n" "$issue_id"
}

_print_blocked_marker() {
  local name="$1"
  local output_file="$2"
  local issue
  issue="$(_file_commit_blocker "$name" "$output_file")"
  if [[ "$issue" == "unfiled" ]]; then
    printf "[COMMIT BLOCKED: %s; AutoIssue=unfiled]\n" "$name" >&2
    return 0
  fi
  if [[ "$issue" == *"("* ]]; then
    printf "[COMMIT BLOCKED: %s; AutoIssue=#%s]\n" "$name" "$issue" >&2
    return 0
  fi
  printf "[COMMIT BLOCKED: %s; AutoIssue=#%s]\n" "$name" "$issue" >&2
}

_run_gate() {
  local mode="$1"
  local name="$2"
  shift 2
  hooks_ran=$((hooks_ran + 1))

  local output_file
  local code
  output_file="$(mktemp "${TMPDIR:-/tmp}/xf-hook-output.XXXXXX")"
  set +e
  "$@" > "$output_file" 2>&1
  code=$?
  set -e

  if [[ -s "$output_file" ]]; then
    cat "$output_file" >&2
  fi
  _collect_finding_ids "$output_file"

  if [[ "$code" -eq 0 ]]; then
    rm -f "$output_file"
    return 0
  fi
  if [[ "$mode" == "soft" && "${XF_QUALITY_ENV:-local}" != "ci" ]]; then
    rm -f "$output_file"
    return 0
  fi

  hard_block_failures=$((hard_block_failures + 1))
  _print_blocked_marker "$name" "$output_file"
  rm -f "$output_file"
  _finish_precommit "$code"
}

run_hard_gate() {
  _run_gate hard "$@"
}

run_soft_gate() {
  _run_gate soft "$@"
}

_run_glossary_check() {
  printf "%s\n" "$staged" | xargs python .githooks/check-glossary.py
}

_run_deep_link_check() {
  quality_docker_compose_run precommit-deep-links backend \
    -e COMMIT_SCOPE_PATHS="$staged" \
    sh -lc '
    cd /repo
    python scripts/verify_deep_links.py --paths-env COMMIT_SCOPE_PATHS
  '
}

_reset_findings_transcript

run_hard_gate tool-readiness bash scripts/run-tool-readiness.sh

# 2026-05-23 — Phase L: ABSOLUTE Observability-Always-On rule.  Stopping
# any observability or quality container to dodge a hook is forbidden.
# Spec: docs/specs/fr-observability-always-on-and-no-deferral.md.
run_hard_gate check-observability-stack python .githooks/check-observability-stack.py
# After confirming the stack is running, safely prune Docker (no volumes) and
# confirm the pipeline is actually feeding AutoIssues. Silent sources warn;
# only an unreachable backend blocks.
run_hard_gate check-observability-pipeline python .githooks/check-observability-pipeline.py

staged="$(python scripts/commit_scope.py paths --mode staged || true)"
if [[ -z "$staged" ]]; then
  echo "No staged files found." >&2
  _finish_precommit 0
fi

run_hard_gate check-glossary _run_glossary_check
# 2026-05-23 — Phase L: ABSOLUTE No-Deferral rule.  Forbidden phrases in
# the staged AGENT-HANDOFF diff + bare deferral-marker tokens in
# committed source comments block the commit.  Linked forms that point
# at a real paper-trail or AutoIssue row are accepted.  See the spec
# at docs/specs/fr-observability-always-on-and-no-deferral.md.
run_hard_gate check-no-deferral python .githooks/check-no-deferral.py
run_hard_gate verify-deep-links _run_deep_link_check

# Run hard gates before slower language checks. A hard gate stops this commit
# pass immediately, while soft gates can file findings locally and keep going.
#
# 2026-05-18 — re-wire the TDD-pipeline hooks that were temporarily reverted
# during Commit A's chain-debugging. The chain MUST enforce the pipeline so
# agents cannot ship new production code without strict TDD evidence. See
# AutoIssue #295 (CRITICAL: chain revert dropped TDD-pipeline enforcement).
run_hard_gate check-tdd-preflight python .githooks/check-tdd-preflight.py
run_hard_gate check-no-destructive-docker-commands python .githooks/check-no-destructive-docker-commands.py
run_hard_gate check-mint-first-build python .githooks/check-mint-first-build.py
run_hard_gate check-decision-point python .githooks/check-decision-point.py
run_hard_gate check-session-close python .githooks/check-session-close.py
run_hard_gate check-tdd-strict python .githooks/check-tdd-strict.py
run_hard_gate check-rust-mandate python .githooks/check-rust-mandate.py
run_hard_gate check-lessons-read-at-session-start python .githooks/check-lessons-read-at-session-start.py
run_hard_gate check-gh-actions-read python .githooks/check-gh-actions-read.py
# 2026-05-18 user directive — commit-failure lookup. Refuses any commit that
# has no audit log entry in audit/commit_failures_lookup_log.jsonl under the
# current task_id. Run `manage.py search_commit_failures` once per task.
run_hard_gate check-commit-failures-lookup python .githooks/check-commit-failures-lookup.py
# 2026-05-23 — Phase K.2: Rewrite Quota rule. Code-changing commits
# must produce >= 3 rewrites/refactorings or carry a verified
# [REWRITE QUOTA EXEMPTION:] evidence marker. Spec at
# docs/specs/fr-rewrite-quota-and-exemption.md.
run_hard_gate check-rewrite-quota python .githooks/check-rewrite-quota.py
# 2026-05-23 — Phase K.3: Native Inspection Window (7 days). Edits to
# settled native-language artifacts (Haskell / Rust / Go / C++) need a
# documented reopen marker. Spec at
# docs/specs/fr-native-inspection-and-spec-windows.md.
run_hard_gate check-native-inspection-window python .githooks/check-native-inspection-window.py
# 2026-05-23 — Phase K.3: Settled-Spec Window (14 days). Edits to
# settled docs/specs/*.md need a documented reopen marker (user
# request, citation drift, or KPI drift).
run_hard_gate check-spec-window python .githooks/check-spec-window.py
run_hard_gate check-autoissue-quota python .githooks/check-autoissue-quota.py
# Always-on, drought-aware per-source quotas (pgexporter health now; Phase B
# adds compiler warnings). Blocks while a source has >= threshold open
# findings unless threshold were resolved this session; 0 open never blocks.
run_hard_gate check-always-on-quota python .githooks/check-always-on-quota.py
run_hard_gate check-codeql-autoissues python .githooks/check-codeql-autoissues.py
run_hard_gate check-gwp-asan python .githooks/check-gwp-asan.py
run_hard_gate check-paper-trail-evidence python .githooks/check-paper-trail-evidence.py
run_hard_gate check-deferral-filed python .githooks/check-deferral-filed.py
run_hard_gate check-profiling-proof python .githooks/check-profiling-proof.py
run_hard_gate check-perf-proof python .githooks/check-perf-proof.py
run_hard_gate check-tdd-cycle python .githooks/check-tdd-cycle.py
run_hard_gate check-scoped-lessons python .githooks/check-scoped-lessons.py
run_hard_gate check-debug-code python .githooks/check-debug-code.py
run_hard_gate check-junk-files python .githooks/check-junk-files.py
# Slice 1.5 — Go services tier boundary + contract enforcement.
run_hard_gate check-no-cross-language-import python .githooks/check-no-cross-language-import.py
# Wrong-language IMPLEMENTATIONS (distinct from the import boundary above):
# MinHash/LSH in Python (belongs in C++), HTTP servers in Python (belongs in
# Go), domain-invariant classifiers in Python services (belongs in Haskell),
# Postgres-owning Go services (belongs in Django).
run_hard_gate check-language-ownership python .githooks/check-language-ownership.py
# Rules J + L (2026-05-16) — C++ kernel lifecycle invariant + stubs only
# move when the contract moves. Both fire only when relevant paths are in
# the staged diff so they cost nothing on unrelated commits.
run_hard_gate check-cpp-lifecycle python .githooks/check-cpp-lifecycle.py
run_hard_gate check-stubs-not-regenerated python .githooks/check-stubs-not-regenerated.py

if grep -E '^backend/.*\.py$|^scripts/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate check-mutable-defaults python .githooks/check-mutable-defaults.py
fi

if grep -E '^backend/config/(settings/|asgi\.py|wsgi\.py|urls\.py)' <<<"$staged" >/dev/null; then
  run_hard_gate check-django-deploy python .githooks/check-django-deploy.py
fi

if grep -E '^backend/apps/.*/models\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate check-fk-on-delete python .githooks/check-fk-on-delete.py
fi

if grep -E '^backend/apps/.*/management/commands/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate check-mgmt-command-dry-run python .githooks/check-mgmt-command-dry-run.py
fi

# Scoped mutation testing fires only when backend Python is staged.
if grep -E '^backend/apps/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate check-scoped-mutation python .githooks/check-scoped-mutation.py
fi

# Compiled code must build AND run. Fires only when a compiled-language file
# is staged. Runs a fast build+test of the affected target before the heavy
# per-language quality runners below, so a non-compiling change fails early.
if grep -E '\.(go|cpp|h|rs|hs)$' <<<"$staged" >/dev/null; then
  run_hard_gate check-compiled-build python .githooks/check-compiled-build.py
fi

# Heavy per-language quality runners (Phase J.6 CI offload — 2026-05-22).
# Each runner executes the full toolchain (ng test + eslint + stylelint +
# Stryker for Angular; pytest + ruff + mypy + mutmut for Python; clang-
# format + clang-tidy + cppcheck + ctest for C++; gofmt + go vet +
# golangci-lint + go test for Go). On a developer workstation these
# routinely take 10-30 minutes per run and surface real test work that
# belongs to the language's own CI suite, not the pre-commit gate.
#
# Behaviour:
#   - `run_soft_gate` writes the finding but does NOT block the commit
#     locally (XF_QUALITY_ENV defaults to `local`).
#   - In CI (XF_QUALITY_ENV=ci) `run_soft_gate` HARD-BLOCKS exactly like
#     `run_hard_gate` — see scripts/precommit-docker.sh:203.
#
# The CI workflows at .github/workflows/ci-language-quality.yml run
# these gates with XF_QUALITY_ENV=ci so they remain authoritative for
# pull requests and main-branch pushes.

if grep -E '^frontend/.*\.(ts|html|scss)$' <<<"$staged" >/dev/null; then
  run_soft_gate run-angular-quality bash scripts/run-angular-quality.sh
fi

if grep -E '^backend/.*\.py$' <<<"$staged" >/dev/null; then
  run_hard_gate run-python-repo-mutation bash scripts/run-python-repo-mutation.sh
  # Python quality always stays HARD because pytest + ruff are part of
  # the strict-TDD discipline and are fast (<2 min for focused tests).
  run_hard_gate run-python-quality bash scripts/run-python-quality.sh
fi

if grep -E '^backend/extensions/.*\.(cpp|h)$' <<<"$staged" >/dev/null; then
  run_soft_gate run-cpp-quality bash scripts/run-cpp-quality.sh
fi

if grep -E '(^|/)go\.(mod|sum)$|\.go$' <<<"$staged" >/dev/null; then
  run_soft_gate run-go-quality bash scripts/run-go-quality.sh
fi

run_soft_gate run-rust-quality    bash scripts/run-rust-quality.sh
run_soft_gate run-haskell-quality bash scripts/run-haskell-quality.sh

run_soft_gate run-quality-debt-report bash scripts/run-quality-debt-report.sh --changed
run_soft_gate agent-guard docker compose exec -T backend python /repo/scripts/agent_guard.py $staged

# Turbo mutation mode: when XF_TURBO_MUTATION=1, run the weighted N-way split
# coordinator for each staged language after all other quality gates
# (Dell up to 60% / Windows 30% / Mint 10%; an offline machine redistributes).
# The individual language quality scripts skip their embedded mutation
# step (checked via XF_TURBO_MUTATION inside each script) and turbo
# runs every reachable machine simultaneously for maximum speed.
if [[ "${XF_TURBO_MUTATION:-0}" == "1" ]]; then
  if grep -qE '^backend/.*\.py$' <<<"$staged"; then
    run_soft_gate turbo-mutation-python python scripts/turbo_mutation.py --language python
  fi
  if grep -qE '^backend/extensions/.*\.(cpp|h)$' <<<"$staged"; then
    run_soft_gate turbo-mutation-cpp python scripts/turbo_mutation.py --language cpp
  fi
  if grep -qE '(^|/)go\.(mod|sum)$|\.go$' <<<"$staged"; then
    run_soft_gate turbo-mutation-go python scripts/turbo_mutation.py --language go
  fi
  if grep -qE '\.rs$|Cargo\.(toml|lock)' <<<"$staged"; then
    run_soft_gate turbo-mutation-rust python scripts/turbo_mutation.py --language rust
  fi
  if grep -qE '\.hs$|\.cabal$' <<<"$staged"; then
    run_soft_gate turbo-mutation-haskell python scripts/turbo_mutation.py --language haskell
  fi
  if grep -qE '^frontend/.*\.(ts|html|scss)$' <<<"$staged"; then
    run_soft_gate turbo-mutation-typescript python scripts/turbo_mutation.py --language typescript
  fi
fi

# Turbo test mode (XF_TURBO_TESTS=1)
if [[ "${XF_TURBO_TESTS:-0}" == "1" ]]; then
  log "info" "Turbo test mode: distributing pytest shards across Dell/Windows/Mint"
  run_hard_gate turbo-tests python /repo/scripts/turbo_tests.py --language python
fi

# Run compiled-language quality shards on Mint and Dell in parallel.
# Both shards run the same toolchain (clang-tidy, ctest, go test, cargo test,
# hlint, etc.) against the same source tree.  Firing them simultaneously halves
# wall-clock time for C++/Go/Rust/Haskell quality when both machines are online.
# An offline machine is non-fatal: its shard exits non-zero and the combined
# check fails, which prompts the agent to bring the machine back online.
if grep -qE '^backend/extensions/.*\.(cpp|h)$|(^|/)go\.(mod|sum)$|\.go$|\.rs$|Cargo\.(toml|lock)|\.hs$|\.cabal$' <<<"$staged"; then
  manifest_json="$(python scripts/plan-scoped-quality-shards.py --mode "${COMMIT_SCOPE_MODE:-push}" 2>/dev/null || echo '{}')"

  # Mint shard — via SSH (Mint is a Linux helper machine)
  (printf "%s" "$manifest_json" | \
    bash scripts/run-mint-quality-shard.sh) &
  MINT_PID=$!

  # Dell shard — via docker --context dell (Dell is a remote Docker host)
  (printf "%s" "$manifest_json" | \
    bash scripts/run-dell-quality-shard.sh) &
  DELL_PID=$!

  wait $MINT_PID; MINT_RC=$?
  wait $DELL_PID; DELL_RC=$?

  if [[ $MINT_RC -ne 0 || $DELL_RC -ne 0 ]]; then
    printf "FAIL compiled-quality-shards: Mint exit=%s Dell exit=%s\n" \
      "$MINT_RC" "$DELL_RC" >&2
    printf "WHY: one or both remote quality shards reported a failure in the compiled-language checks.\n" >&2
    printf "UNBLOCK: check Mint and Dell docker context connectivity, then rerun the commit.\n" >&2
    _finish_precommit 1
  fi
fi

quality_artifact_safe_prune_host
_finish_precommit 0
