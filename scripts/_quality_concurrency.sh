#!/usr/bin/env bash
# Shared concurrency + wall-clock-cap + container-cleanup helpers for
# every scripts/run-*-quality.sh and scripts/run-*-mutation.sh script.
#
# Per the local test resource policy in CLAUDE.md + docs/CI-GATES.md:
#
#   - Local quality gates run sequentially. Agents must not run
#     multiple heavy quality tools at the same time.
#   - Forbidden: parallel backend+frontend tests, parallel coverage+
#     mutation runs, background test jobs, multiple frontend test
#     commands in parallel.
#   - Every local quality tool has a 5-minute hard wall-clock cap.
#   - Local checks use one worker. GitHub Actions may request more.
#   - GitHub Actions (XF_QUALITY_ENV=ci) bypasses caps.
#
# Source this file at the top of every run-*-quality.sh:
#
#   . scripts/_quality_concurrency.sh
#   quality_acquire_meta_lock
#   quality_install_cleanup_trap
#
# Then for each tool invocation:
#
#   quality_acquire_tool_lock stryker
#   QUALITY_CONTAINER="$(quality_docker_container_name stryker)"
#   docker compose run --rm -T --no-deps --name "$QUALITY_CONTAINER" ...
#   quality_register_container "$QUALITY_CONTAINER"
#   quality_timeout 300 some-command
#
# Why each piece exists:
#
#   meta-lock      -> stops two run-*-quality.sh scripts running in
#                     parallel anywhere in the repo
#   tool-lock      -> stops two invocations of the same tool racing
#                     each other (e.g. lint-all.ps1 + precommit
#                     touching the same Stryker container slot)
#   container name -> docker compose run is otherwise anonymous; a
#                     stable --name lets the cleanup trap remove the
#                     container even if the wrapper dies. Today (2026-
#                     05-17) two anonymous Stryker containers ran for
#                     1h17m because TaskStop killed the bash wrapper
#                     but not the docker process; this helper fixes
#                     that family of bugs.
#   timeout cap    -> 5-minute hard wall-clock limit. On timeout, the
#                     helper emits a Rule-F three-part error pointing
#                     at the three accepted resolutions: narrow target,
#                     move to GitHub Actions, or mark remote-only.
#   cleanup trap   -> on EXIT/INT/TERM (success, failure, signal),
#                     the trap force-removes every container the
#                     wrapper started. No more orphans.

set -u

# Docker-only: Git 2.35+ rejects bind-mounted repos owned by a
# different host UID unless the exact path is marked safe. Keep this
# scoped to /repo and do not alter host Git config.
if [ -f /.dockerenv ]; then
  git config --global --add safe.directory /repo 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Configuration (env-overridable).
# ---------------------------------------------------------------------------

# Lock files live here. Defaulted under /tmp so a fresh shell starts
# clean; persistent storage would risk stale locks across reboots.
QUALITY_LOCK_DIR="${QUALITY_LOCK_DIR:-/tmp/xf-quality-locks}"
mkdir -p "$QUALITY_LOCK_DIR"

# local vs ci. CI workflows MUST export XF_QUALITY_ENV=ci so the caps
# are bypassed (GitHub Actions may legitimately need 30+ min for a
# scoped mutation pass).
QUALITY_ENV="${XF_QUALITY_ENV:-local}"

# Hard 5-min wall-clock cap on every local quality tool. The
# policy is firm: no XF_QUALITY_TIMEOUT_OVERRIDE escape hatch. If a
# tool can't finish in 5 min, narrow the scope, move it to CI, or
# add a [REMOTE-ONLY CHECK: ...] marker to the handoff entry.
QUALITY_CAP_SECONDS="${QUALITY_CAP_SECONDS:-300}"

# Containers started by the current wrapper. Cleanup removes them on
# EXIT/INT/TERM. Bash arrays are local-by-default in subshells; this
# array is global so cleanup sees every container.
declare -ga QUALITY_CONTAINERS=()

# Track which FDs we've claimed for flock so the cleanup releases them
# on exit. (Bash auto-closes them on exit anyway; this is belt-and-
# braces.)
declare -ga QUALITY_LOCK_FDS=()

# Bash file-descriptor counter. flock needs an explicit FD per lock;
# we start at 9 (system-reserved FDs are 0/1/2; awk/sed and friends
# sometimes touch 3-8; 9+ is safe).
QUALITY_NEXT_FD=9

# ---------------------------------------------------------------------------
# Internal: emit a Rule-F three-part error.
# ---------------------------------------------------------------------------

_quality_fail_rule_f() {
  # Args: <what> <why> <unblock>
  local what="$1"
  local why="$2"
  local unblock="$3"
  echo "FAIL _quality_concurrency: $what" >&2
  echo "WHY: $why" >&2
  echo "UNBLOCK: $unblock" >&2
}

# ---------------------------------------------------------------------------
# Meta-lock: one quality script repo-wide at a time.
# ---------------------------------------------------------------------------

quality_acquire_meta_lock() {
  # No-op: the sequential gate is replaced by the parallel orchestrator
  # (scripts/run-scoped-static-quality.ps1). The per-tool lock
  # (quality_acquire_tool_lock) still prevents two mutmut or two mull
  # runs from colliding with each other.
  return 0
}

# ---------------------------------------------------------------------------
# Per-tool lock: one Stryker, one mutmut, etc. at a time.
# ---------------------------------------------------------------------------

quality_acquire_tool_lock() {
  local tool="$1"
  local lockfile="$QUALITY_LOCK_DIR/$tool.lock"
  if command -v flock >/dev/null 2>&1; then
    local fd="$QUALITY_NEXT_FD"
    QUALITY_NEXT_FD=$((QUALITY_NEXT_FD + 1))
    # shellcheck disable=SC2093
    eval "exec $fd>'$lockfile'"
    if ! flock -n "$fd"; then
      _quality_fail_rule_f \
        "another '$tool' run is in progress (tool-lock held)" \
        "tool-level lock $lockfile prevents two concurrent invocations of the same tool" \
        "wait for the running '$tool' to finish, check 'docker ps' for orphan '$(quality_docker_container_name "$tool")' containers, or rm $lockfile if you know it's stale"
      exit 2
    fi
    QUALITY_LOCK_FDS+=("$fd")
  else
    if ! mkdir "$lockfile.d" 2>/dev/null; then
      _quality_fail_rule_f \
        "tool-lock $lockfile.d already held for '$tool'" \
        "two parallel invocations of the same tool" \
        "wait, or rmdir $lockfile.d if stale"
      exit 2
    fi
  fi
}

# ---------------------------------------------------------------------------
# Stable container name per tool so cleanup can find + kill it.
# ---------------------------------------------------------------------------

quality_docker_container_name() {
  local tool="$1"
  echo "xf-quality-$tool"
}

# Register a container the wrapper started so cleanup kills it.
quality_register_container() {
  local container="$1"
  QUALITY_CONTAINERS+=("$container")
}

# ---------------------------------------------------------------------------
# Cleanup trap: kill every registered container on EXIT/INT/TERM and
# release lockdir-fallback locks.
# ---------------------------------------------------------------------------

quality_cleanup() {
  local rc=$?
  # Kill every container we registered. `|| true` because the
  # container may have already exited normally; we just want to be
  # sure no orphan survives.
  if [ "${#QUALITY_CONTAINERS[@]}" -gt 0 ]; then
    for container in "${QUALITY_CONTAINERS[@]}"; do
      [ -z "$container" ] && continue
      docker rm -f "$container" >/dev/null 2>&1 || true
    done
  fi
  # Release any lockdir-fallback locks (flock locks auto-release on
  # FD close at process exit; the mkdir fallback needs explicit rmdir).
  for lockd in "$QUALITY_LOCK_DIR"/*.lock.d; do
    [ -d "$lockd" ] && rmdir "$lockd" 2>/dev/null || true
  done
  return "$rc"
}

quality_install_cleanup_trap() {
  # Bash's EXIT trap fires on normal exit. INT (Ctrl-C) and TERM
  # (SIGTERM from TaskStop or pre-commit timeout) both also need
  # cleanup so the container dies with the wrapper.
  trap quality_cleanup EXIT
  trap 'quality_cleanup; exit 130' INT
  trap 'quality_cleanup; exit 143' TERM
}

# ---------------------------------------------------------------------------
# Wall-clock timeout wrapper. Skipped in CI.
# ---------------------------------------------------------------------------

_quality_resolve_gnu_timeout() {
  # On Windows + Git Bash, /c/Windows/system32/timeout shadows GNU's.
  # Use the absolute Git Bash path if it exists, else verify the one
  # on PATH is GNU's.
  if [ -x /usr/bin/timeout ] && /usr/bin/timeout --version 2>/dev/null | head -1 | grep -q "GNU coreutils"; then
    echo /usr/bin/timeout
    return 0
  fi
  if [ -x /usr/bin/timeout.exe ] && /usr/bin/timeout.exe --version 2>/dev/null | head -1 | grep -q "GNU coreutils"; then
    echo /usr/bin/timeout.exe
    return 0
  fi
  if command -v timeout >/dev/null 2>&1 && timeout --version 2>/dev/null | head -1 | grep -q "GNU coreutils"; then
    command -v timeout
    return 0
  fi
  return 1
}

quality_timeout() {
  local seconds="$1"; shift
  if [ "$QUALITY_ENV" = "ci" ]; then
    "$@"
    return $?
  fi
  local gnu_timeout
  if gnu_timeout="$(_quality_resolve_gnu_timeout)"; then
    # SIGTERM first (graceful 30s drain), SIGKILL second.
    "$gnu_timeout" --signal=TERM --kill-after=30 "$seconds" "$@"
    local rc=$?
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
      _quality_fail_rule_f \
        "local quality command exceeded ${seconds}s wall-clock cap" \
        "local test resource policy gives every quality tool a hard 5-min cap; this command did not finish in time" \
        "either (a) narrow the target so the scoped run fits the budget, (b) move the heavy check to GitHub Actions (the workflow runs uncapped on push + PR events), or (c) add a [REMOTE-ONLY CHECK: tool=<name> reason=\"<>=20-char plain English>\"] marker to the handoff entry"
      return "$rc"
    fi
    return "$rc"
  fi
  _quality_fail_rule_f \
    "GNU coreutils timeout is required for local quality checks" \
    "the sequential quality policy forbids background PID timeout fallbacks, so the helper cannot use '&' and 'wait' when GNU timeout is missing" \
    "run the check through the Docker-managed tool image, install GNU coreutils timeout for this shell, or move the heavy check to GitHub Actions"
  return 2
}

# ---------------------------------------------------------------------------
# Worker count. Local checks stay serial; CI may request more.
# ---------------------------------------------------------------------------

quality_check_scope_cap() {
  local wrapper="$1"; shift
  local tool="$1"; shift
  local max_files="$1"; shift
  local targets="${1:-}"
  if [ -z "$targets" ]; then
    return 0
  fi
  printf "%s\n" $targets | python scripts/scope_cap.py "$tool" "$max_files" --stdin
}

quality_log_scope_skip() {
  local wrapper="$1"; shift
  local tool="$1"; shift
  local max_files="$1"; shift
  echo "SKIP scope cap: $wrapper has no $tool targets (cap=$max_files)."
}

quality_log_scope_decision() {
  local wrapper="$1"; shift
  local tool="$1"; shift
  local detail="$1"; shift
  echo "SCOPE decision: $wrapper $tool $detail."
}

quality_cores() {
  local requested="${XF_QUALITY_CORES:-1}"
  local max_plugged=1
  local max_battery=1
  # CI: trust the workflow's request without clamping.
  if [ "$QUALITY_ENV" = "ci" ]; then
    echo "$requested"
    return
  fi
  # Best-effort cross-platform power-state detection. Returns 1 if
  # plugged in, 0 otherwise.
  local plugged=0
  if [ -d /sys/class/power_supply ]; then
    # Linux. Any AC adapter online -> plugged.
    for ac in /sys/class/power_supply/AC*; do
      if [ -f "$ac/online" ] && [ "$(cat "$ac/online" 2>/dev/null)" = "1" ]; then
        plugged=1
        break
      fi
    done
  elif command -v pmset >/dev/null 2>&1; then
    # macOS.
    if pmset -g batt 2>/dev/null | grep -q "AC Power"; then
      plugged=1
    fi
  elif command -v powercfg.exe >/dev/null 2>&1; then
    # Windows. powercfg returns the active scheme; a heuristic is the
    # presence of "AC" in 'powercfg /a'. Treat unknown as battery.
    if powercfg.exe /a 2>/dev/null | grep -qi "AC"; then
      plugged=1
    fi
  fi
  # Inside Docker containers, /sys/class/power_supply is empty.
  # Assume plugged-in for container runs (typically a dev workstation
  # on AC or a CI runner).
  if [ -f /.dockerenv ] && [ "$plugged" -eq 0 ]; then
    plugged=1
  fi
  local cap=$max_battery
  [ "$plugged" -eq 1 ] && cap=$max_plugged
  # Clamp `requested` to `cap`. min(requested, cap).
  if [ "$requested" -gt "$cap" ]; then
    echo "$cap"
  else
    echo "$requested"
  fi
}

# ---------------------------------------------------------------------------
# Convenience: invoke `docker compose run` with the named-container +
# auto-cleanup pattern. Caller supplies the service name and any extra
# flags; the helper inserts --rm -T --no-deps --name <stable-name>.
# ---------------------------------------------------------------------------

quality_docker_compose_run() {
  # wrapper-parses-docker-options-before-service
  # Signature: quality_docker_compose_run <tool> <service> [docker-options...] [-- ] [command...]
  #
  # Docker compose run expects options before the service name. The helper
  # accepts caller-supplied docker options after <service> for readability,
  # then moves the recognised options before the service in the real call.
  local tool="$1"; shift
  local service="$1"; shift
  local -a docker_opts=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --)
        shift
        break
        ;;
      -e|--env|-v|--volume|-w|--workdir|-u|--user|-l|--label|--entrypoint|--env-from-file|--env-file|--add-host|-p|--publish|--pull|--cap-add|--cap-drop|--cpus|--memory)
        if [[ $# -lt 2 ]]; then
          _quality_fail_rule_f \
            "docker option '$1' is missing its value" \
            "quality_docker_compose_run recognises '$1' as a flag that needs a value" \
            "pass the value as the next token, or use '--' to mark the command boundary"
          return 2
        fi
        docker_opts+=("$1" "$2")
        shift 2
        ;;
      -e=*|--env=*|-v=*|--volume=*|-w=*|--workdir=*|-u=*|--user=*|-l=*|--label=*|--entrypoint=*|--env-file=*|--add-host=*|--pull=*)
        docker_opts+=("$1")
        shift
        ;;
      --build|-d|--detach|-i|--interactive|--remove-orphans|-P|--service-ports|--use-aliases|-q|--quiet-pull)
        docker_opts+=("$1")
        shift
        ;;
      *)
        break
        ;;
    esac
  done
  local container
  container="$(quality_docker_container_name "$tool")"
  if [[ "${XF_QUALITY_NO_BUILD:-0}" == "1" ]]; then
    docker_opts=(--pull never "${docker_opts[@]}")
  fi
  # If a container with this name already exists, fail fast — it
  # means an earlier run leaked. The cleanup trap should normally
  # prevent this, but defense in depth.
  if docker ps -a --filter "name=^${container}$" --format '{{.Names}}' 2>/dev/null | grep -qx "$container"; then
    _quality_fail_rule_f \
      "container '$container' already exists" \
      "an earlier '$tool' run leaked its container; the cleanup trap should have removed it" \
      "run 'docker rm -f $container' if you know it's stale, then retry"
    return 2
  fi
  quality_register_container "$container"
  if [[ ${#docker_opts[@]} -gt 0 ]]; then
    docker compose run --rm -T --no-deps --name "$container" "${docker_opts[@]}" "$service" "$@"
  else
    docker compose run --rm -T --no-deps --name "$container" "$service" "$@"
  fi
}
