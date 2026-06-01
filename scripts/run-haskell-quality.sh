#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
. "$repo_root/scripts/_quality_concurrency.sh"
. "$repo_root/scripts/quality_cores.sh"
. "$repo_root/scripts/_compiler_warnings_lib.sh"
compiler_warnings_init haskell
haskell_warning_log="$repo_root/$(compiler_warnings_log_path haskell)"

workspace="${HASKELL_WORKSPACE:-$repo_root/services/findbugs-haskell}"
workers="$(quality_cores cabal-test)"
hlint_workers="$(quality_cores hlint)"

# Scope guard: skip entirely when no Haskell-relevant files changed.
# In CI set COMMIT_SCOPE_MODE=push; locally defaults to staged.
# Matches: *.hs, *.cabal, stack.yaml, cabal.project
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
hs_paths="$(python "$repo_root/scripts/commit_scope.py" paths --mode "$scope_mode" \
  | grep -E '\.hs$|\.cabal$|stack\.yaml$|cabal\.project$' || true)"
if [[ -z "$hs_paths" ]]; then
  echo "[run-haskell-quality] No changed Haskell files detected -- skipping."
  exit 0
fi
hs_file_count="$(echo "$hs_paths" | wc -l | tr -d ' ')"
echo "[run-haskell-quality] Scoped to $hs_file_count changed Haskell file(s)."
export QUALITY_HASKELL_PATHS="$hs_paths"

if [[ ! -f "$workspace/findbugs-haskell.cabal" ]]; then
  echo "No Haskell cabal file found at $workspace."
  exit 0
fi

cd "$workspace"
if command -v hlint >/dev/null 2>&1; then
  echo "+ hlint -j $hlint_workers ."
  # Tee hlint's combined stdout+stderr into the compiler-warning log, then
  # ingest the captured diagnostics (non-fatal) BEFORE re-raising any hlint
  # failure, so warnings are filed even on a failing hlint run.
  # pipefail+PIPESTATUS[0] recovers hlint's real exit code (tee always succeeds).
  set +e
  set -o pipefail
  hlint -j "$hlint_workers" . 2>&1 | tee -a "$haskell_warning_log"
  hlint_rc="${PIPESTATUS[0]}"
  set -e
  ( cd "$repo_root" && compiler_warnings_ingest haskell )
  if [[ "$hlint_rc" -ne 0 ]]; then
    exit "$hlint_rc"
  fi
else
  echo "hlint not installed; skipping Haskell lint."
fi
echo "+ cabal test --jobs=$workers"
cabal test --jobs="$workers" all --builddir=/tmp/xf-build/findbugs-haskell-dist
if [[ "${XF_TURBO_MUTATION:-0}" == "1" ]]; then
  echo "[run-haskell-quality] XF_TURBO_MUTATION=1: Haskell mutation delegated to turbo coordinator (65/35 split via turbo_mutation.py)"
elif command -v mucheck >/dev/null 2>&1; then
  echo "+ mucheck (Haskell mutation, timeout 60 s per module)"
  mucheck --timeout 60 --module-dir . --test-suite all || \
    echo "WARN: mucheck exited non-zero; review findings above."
else
  echo "[run-haskell-quality] mucheck not installed; skipping Haskell mutation."
fi
