#!/usr/bin/env bash
# Dell-only execution lock for the local Windows machine ("MSI").
#
# Tests, lint, coverage, and mutation runs are FORBIDDEN on this Windows
# host — the Dell helper carries 100% of that work. These functions let
# the quality and mutation runners refuse any path that would execute
# work locally, even when someone overrides the remote helper or split
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
  # Usage: xf_require_remote_context <runner-label> <remote-helper-name>
  # Blocks the run when the helper names the retired local container engine.
  local label="$1" context="${2:-}"
  xf_on_msi_host || return 0
  case "$context" in
    ""|__local__|local|default|desktop-linux|desktop-windows)
      echo "FAIL $label: tests and mutation runs are blocked on this Windows machine (MSI)." >&2
      echo "WHY: the helper '${context:-<empty>}' is the retired local container engine; all test and mutation work runs on the Dell helper only." >&2
      echo "UNBLOCK: remove the helper override (the default is 'dell'), or fix SSH access to Dell, then re-run." >&2
      exit 1
      ;;
  esac
}

xf_prepare_ssh_home() {
  # Git Bash usually creates HOME for interactive shells, but Bazel-launched
  # sh_binary targets may inherit only the Windows profile variables. SSH needs
  # HOME so it can read the same keys and config the terminal uses.
  [[ -n "${HOME:-}" ]] && return 0
  local candidate="${USERPROFILE:-}"
  if [[ -z "$candidate" && -n "${HOMEDRIVE:-}" && -n "${HOMEPATH:-}" ]]; then
    candidate="${HOMEDRIVE}${HOMEPATH}"
  fi
  if [[ -z "$candidate" ]]; then
    for powershell_path in \
      powershell.exe \
      /c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
    do
      if command -v "$powershell_path" >/dev/null 2>&1 || [[ -x "$powershell_path" ]]; then
        candidate="$("$powershell_path" -NoProfile -Command '[Environment]::GetFolderPath("UserProfile")' 2>/dev/null | tr -d '\r')"
        [[ -n "$candidate" ]] && break
      fi
    done
  fi
  [[ -n "$candidate" ]] || return 0
  if command -v cygpath >/dev/null 2>&1; then
    HOME="$(cygpath -u "$candidate")"
  else
    HOME="$candidate"
  fi
  export HOME
}

xf_remote_context_reachable() {
  # Usage: xf_remote_context_reachable <remote-helper-name> [attempts] [sleep_seconds]
  # Probe `ssh <host> docker version` with retries. The FIRST SSH/docker call
  # to an idle Dell frequently times out on a cold connection, so a single-shot
  # probe reports a false "unreachable" and wrongly blocks the commit. Retrying
  # mirrors the resilience already in scripts/machine_routing.py. Returns 0 as
  # soon as the context answers, non-zero only after all attempts fail.
  local context="$1" attempts="${2:-3}" sleep_s="${3:-2}" i last_error=""
  if [[ "$context" == "__local__" || "$context" == "local" ]]; then
    docker version >/dev/null 2>&1
    return $?
  fi
  xf_prepare_ssh_home
  local ssh_args=(-o BatchMode=yes -o ConnectTimeout=10)
  if [[ -n "${HOME:-}" && -f "${HOME}/.ssh/config" ]]; then
    ssh_args+=(-F "${HOME}/.ssh/config")
  fi
  for (( i = 1; i <= attempts; i++ )); do
    last_error="$(ssh "${ssh_args[@]}" "$context" docker version 2>&1 >/dev/null)" && return 0
    if [[ -n "$last_error" && "$i" -eq "$attempts" ]]; then
      printf 'Dell probe context: home=%s config=%s\n' "${HOME:-<unset>}" "${HOME:+${HOME}/.ssh/config}" >&2
      printf 'Dell probe failed: %s\n' "$last_error" >&2
    fi
    if [[ -n "$last_error" && "$i" -lt "$attempts" && "${XF_DELL_PROBE_DEBUG:-0}" == "1" ]]; then
      printf 'Dell probe attempt %s failed: %s\n' "$i" "$last_error" >&2
    fi
    if [[ -z "$last_error" && "$i" -eq "$attempts" ]]; then
      printf 'Dell probe failed without SSH output.\n' >&2
    fi
    if [[ -z "$last_error" && "${XF_DELL_PROBE_DEBUG:-0}" == "1" ]]; then
      printf 'Dell probe attempt %s failed without SSH output.\n' "$i" >&2
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
