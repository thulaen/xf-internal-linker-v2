#!/usr/bin/env bash
# Dell-only execution lock for the local Windows machine ("MSI").
#
# Tests, lint, coverage, and mutation runs are FORBIDDEN on this Windows
# host — the Dell helper carries 100% of that work. These functions let
# the quality and mutation runners refuse any path that would execute
# work locally, even when someone overrides the docker-context or split
# environment variables. CI runners (CI / GITHUB_ACTIONS set) and
# containers are exempt: the lock targets exactly one machine — the
# local Windows desktop.

xf_on_msi_host() {
  # True only on the bare Windows host: not in a container, not in CI.
  # WSL counts as the Windows host — it is the same physical machine.
  [[ -f /.dockerenv ]] && return 1
  [[ "${GITHUB_ACTIONS:-}" == "true" || "${CI:-}" == "true" ]] && return 1
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  [[ "${OS:-}" == "Windows_NT" ]] && return 0
  grep -qi microsoft /proc/version 2>/dev/null && return 0
  return 1
}

xf_require_remote_context() {
  # Usage: xf_require_remote_context <runner-label> <docker-context-name>
  # Blocks the run when the context names the LOCAL Docker Desktop engine.
  local label="$1" context="${2:-}"
  xf_on_msi_host || return 0
  case "$context" in
    ""|default|desktop-linux|desktop-windows)
      echo "FAIL $label: tests and mutation runs are blocked on this Windows machine (MSI)." >&2
      echo "WHY: the docker context '${context:-<empty>}' is the local Docker Desktop engine; all test and mutation work runs on the Dell helper only." >&2
      echo "UNBLOCK: remove the context override (the default is 'dell'), or fix the Dell docker context, then re-run." >&2
      exit 1
      ;;
  esac
}

xf_remote_context_reachable() {
  # Usage: xf_remote_context_reachable <docker-context-name> [attempts] [sleep_seconds]
  # Probe `docker --context <ctx> info` with retries. The FIRST SSH/docker call
  # to an idle Dell frequently times out on a cold connection, so a single-shot
  # probe reports a false "unreachable" and wrongly blocks the commit. Retrying
  # mirrors the resilience already in scripts/machine_routing.py. Returns 0 as
  # soon as the context answers, non-zero only after all attempts fail.
  local context="$1" attempts="${2:-3}" sleep_s="${3:-2}" i
  for (( i = 1; i <= attempts; i++ )); do
    if docker --context "$context" version >/dev/null 2>&1; then
      return 0
    fi
    if [[ "$i" -lt "$attempts" ]]; then
      sleep "$sleep_s"
    fi
  done
  return 1
}

xf_block_local_quality_container() {
  # Usage: xf_block_local_quality_container <runner-label>
  # Hard-stops the in-container quality path on the Windows host.
  local label="$1"
  xf_on_msi_host || return 0
  echo "FAIL $label: running quality tools in the local backend-quality container is blocked on this Windows machine (MSI)." >&2
  echo "WHY: lint, types, security, tests, coverage, and mutation all run on the Dell helper; the in-container path exists only for CI runners." >&2
  echo "UNBLOCK: remove the XF_LINT_SPLIT / XF_PYTEST_SPLIT / XF_QUALITY_ENV overrides so the Dell split runs, or fix the Dell docker context, then re-run." >&2
  exit 1
}
