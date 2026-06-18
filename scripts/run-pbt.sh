#!/usr/bin/env bash
# Property-based testing (PBT) gate — PRE-COMMIT, DELL-ONLY, scoped to changed
# files. Python uses Hypothesis; Rust uses proptest. Top-level script property
# tests use Hypothesis too. All lanes run under the "fast" profile (few
# examples) so the commit stays a quick sprint. A single wall-clock timeout is
# the hard time ceiling.
#
# This is a separate lane from mutation testing: PBT runs here at pre-commit,
# mutation runs at pre-push, so the two never execute at the same time and use
# different Dell volumes.
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

# Resolve a python interpreter (git-hook shells strip PATH).
PY="python"
if ! command -v "$PY" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then PY="python3"; else
    for _c in "/c/Program Files/Python312/python.exe" "/c/Program Files/Python311/python.exe" "$repo_root/.venv/Scripts/python.exe"; do
      [[ -x "$_c" ]] && { PY="$_c"; break; }
    done
  fi
fi

PBT_DOCKER_CONTEXT="${PBT_DOCKER_CONTEXT:-dell}"
HYPOTHESIS_PROFILE="${HYPOTHESIS_PROFILE:-fast}"
PROPTEST_CASES="${PROPTEST_CASES:-50}"
PBT_TIMEOUT="${PBT_TIMEOUT:-300}"            # TOTAL wall-clock budget (sec) — 5 min
PY_IMAGE="xf-linker-backend-quality:latest"
RUST_IMAGE="xf-linker-compiled-mutation-tools:latest"

# Shared 5-minute budget across BOTH lanes: each lane runs under `timeout
# $(_remaining)`, so the whole gate can never exceed PBT_TIMEOUT. A lane that
# would blow the budget is killed and the gate hard-fails (fail-fast at the cap).
gate_start=$(date +%s)
_remaining() { local r=$(( PBT_TIMEOUT - ( $(date +%s) - gate_start ) )); (( r < 1 )) && r=1; echo "$r"; }

. scripts/_dell_only_guard.sh
xf_require_remote_context run-pbt "$PBT_DOCKER_CONTEXT"

# ── Scope to changed / new files ─────────────────────────────────────────────
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
# `tr -d '\r'`: Windows-native python prints CRLF, and a trailing \r makes the
# basename end in ".py\r" so every `*.py` case pattern silently misses. Strip it.
changed="$("$PY" scripts/commit_scope.py paths --mode "$scope_mode" 2>/dev/null | tr -d '\r' || true)"

# Python property tests: a changed tests_pbt_*.py runs directly; a changed
# source file runs its sibling tests_pbt_<stem>.py when one exists. Matching is
# glob-free (parameter expansion) because `case` globs do not cross `/` in the
# git-hook Git Bash, so a `backend/*/tests_pbt_*.py` pattern would silently miss
# deep paths.
py_targets="$(
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    rel="${p#backend/}"
    [[ "$rel" != "$p" ]] || continue          # only backend/ paths
    base="${rel##*/}"                          # basename (single segment)
    case "$base" in
      tests_pbt_*.py) printf '%s\n' "$rel" ;;
      *.py)
        d="${rel%/*}"; s="${base%.py}"
        sib="$d/tests_pbt_${s}.py"
        [[ -f "backend/$sib" ]] && printf '%s\n' "$sib" ;;
    esac
  done <<< "$changed" | sort -u || true
)"

# Top-level script property tests: a changed scripts/tests_pbt_*.py runs
# directly; a changed scripts/<name>.py runs scripts/tests_pbt_<name>.py when
# one exists. This keeps shared agent tools covered by the same PBT gate as
# backend and Rust code.
script_targets="$(
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    rel="${p#scripts/}"
    [[ "$rel" != "$p" ]] || continue
    base="${rel##*/}"
    case "$base" in
      tests_pbt_*.py) printf '%s\n' "$p" ;;
      *.py)
        d="${p%/*}"; s="${base%.py}"
        sib="$d/tests_pbt_${s}.py"
        [[ -f "$sib" ]] && printf '%s\n' "$sib" ;;
    esac
  done <<< "$changed" | sort -u || true
)"

# Rust crates whose files changed (their proptest tests run). Glob-free for the
# same reason.
rust_crates="$(
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    rest="${p#rust/extensions/}"
    if [[ "$rest" != "$p" ]]; then
      printf '%s\n' "${rest%%/*}"              # first segment = crate name
    elif [[ "${p#rust/xf_kernels/}" != "$p" ]]; then
      printf '%s\n' "xf_kernels"
    fi
  done <<< "$changed" | sort -u || true
)"

if [[ -z "$py_targets" && -z "$script_targets" && -z "$rust_crates" ]]; then
  echo "[run-pbt] No changed property-test scope -- skipping."
  exit 0
fi

# Dell uses an SSH transport; the first connection in a fresh process can lose
# a race before the control channel is up, so probe with a few retries.
if ! xf_remote_context_reachable "$PBT_DOCKER_CONTEXT" 4 2; then
  echo "FAIL run-pbt: Dell context '$PBT_DOCKER_CONTEXT' is required and not reachable." >&2
  echo "WHY: property tests run on Dell ONLY; there is no Windows fallback." >&2
  echo "UNBLOCK: wake/fix the Dell Docker context, then retry the commit." >&2
  exit 1
fi

# Core count is ADAPTIVE without an extra probe container: pytest-xdist `-n
# auto` and nextest both read the test container's own CPU count at runtime, so
# parallelism tracks Dell's hardware with zero hardcoding.
echo "[run-pbt] profile=$HYPOTHESIS_PROFILE proptest_cases=$PROPTEST_CASES cores=auto timeout=${PBT_TIMEOUT}s"

rc=0

# PBT reuses the volumes the unit-test gates already populated this commit
# (run-python-quality syncs the whole backend into xf_test_repo;
# run-rust-quality syncs rust/ into xf_rust_mutation_repo). PBT runs right after
# them, so it skips the expensive full-tree upload and only overlays the handful
# of changed files — the dominant cost in an isolated run was that re-upload.
changed_backend="$(printf '%s\n' "$changed" | grep '^backend/' || true)"
changed_scripts="$(printf '%s\n' "$changed" | grep '^scripts/' || true)"
changed_rust="$(printf '%s\n' "$changed" | grep '^rust/' || true)"

# ── Python lane: Hypothesis, parallel via pytest-xdist (-n auto) ──────────────
if [[ -n "$py_targets" ]]; then
  echo "[run-pbt] Python: $(printf '%s' "$py_targets" | grep -c .) property file(s)."
  s0=$(date +%s)
  if [[ -n "$changed_backend" ]]; then
    # shellcheck disable=SC2086
    tar -cf - $changed_backend \
      | "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm -i -v xf_test_repo:/repo \
          alpine:latest sh -c "tar -xf - -C /repo"
  fi
  py_oneline="$(printf '%s' "$py_targets" | tr '\n' ' ')"
  echo "[run-pbt] Python overlay: $(( $(date +%s) - s0 ))s."
  t0=$(date +%s)
  # config.settings.test is the test settings module the normal pytest gate
  # uses. Property tests are pure (no DB/network), so a dummy secret key and
  # placeholder service hosts are enough for django.setup() to import — nothing
  # here ever opens a connection.
  if "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm \
      -v xf_test_repo:/repo -w //repo/backend \
      -e DJANGO_SETTINGS_MODULE=config.settings.test \
      -e DJANGO_SECRET_KEY=pbt-dummy-key-pure-tests-never-use-it \
      -e POSTGRES_HOST=localhost -e POSTGRES_DB=pbt -e POSTGRES_USER=pbt -e POSTGRES_PASSWORD=pbt \
      -e REDIS_URL=redis://localhost:6379/0 -e CELERY_BROKER_URL=redis://localhost:6379/2 \
      -e HYPOTHESIS_PROFILE="$HYPOTHESIS_PROFILE" \
      -e PBT_REMAINING="$(_remaining)" -e PBT_FILES="$py_oneline" \
      "$PY_IMAGE" sh -lc 'timeout "$PBT_REMAINING" python -m pytest $PBT_FILES -m property -p no:randomly -n auto -q -o addopts=--strict-markers'; then
    echo "[run-pbt] Python PBT passed in $(( $(date +%s) - t0 ))s."
  else
    rc=$?; echo "[run-pbt] Python PBT FAILED (rc=$rc) in $(( $(date +%s) - t0 ))s." >&2
  fi
fi

# ── Top-level scripts lane: Hypothesis, parallel via pytest-xdist (-n auto) ──
if [[ -n "$script_targets" ]]; then
  echo "[run-pbt] Scripts: $(printf '%s' "$script_targets" | grep -c .) property file(s)."
  s0=$(date +%s)
  if [[ -n "$changed_scripts" ]]; then
    tar -cf - scripts/*.py scripts/tests/*.py 2>/dev/null \
      | "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm -i -v xf_test_repo:/repo \
          alpine:latest sh -c "mkdir -p /repo && tar -xf - -C /repo"
  fi
  scripts_oneline="$(printf '%s' "$script_targets" | tr '\n' ' ')"
  echo "[run-pbt] Scripts overlay: $(( $(date +%s) - s0 ))s."
  t0=$(date +%s)
  if "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm \
      -v xf_test_repo:/repo -w //repo \
      -e HYPOTHESIS_PROFILE="$HYPOTHESIS_PROFILE" \
      -e PBT_REMAINING="$(_remaining)" -e PBT_FILES="$scripts_oneline" \
      "$PY_IMAGE" sh -lc 'timeout "$PBT_REMAINING" python -m pytest $PBT_FILES -m property -p no:randomly -n auto -q -o addopts=--strict-markers'; then
    echo "[run-pbt] Scripts PBT passed in $(( $(date +%s) - t0 ))s."
  else
    rc=$?; echo "[run-pbt] Scripts PBT FAILED (rc=$rc) in $(( $(date +%s) - t0 ))s." >&2
  fi
fi

# ── Rust lane: proptest, parallel via nextest (auto test-threads) ────────────
if [[ -n "$rust_crates" ]]; then
  echo "[run-pbt] Rust: crate(s): $(printf '%s' "$rust_crates" | tr '\n' ' ')"
  s0=$(date +%s)
  if [[ -n "$changed_rust" ]]; then
    # shellcheck disable=SC2086
    tar -cf - $changed_rust \
      | "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm -i -v xf_rust_mutation_repo:/repo \
          alpine:latest sh -c "tar -xf - -C /repo"
  fi
  pkg_flags=""; while IFS= read -r c; do [[ -n "$c" ]] && pkg_flags="$pkg_flags -p $c"; done <<< "$rust_crates"
  echo "[run-pbt] Rust overlay: $(( $(date +%s) - s0 ))s."
  t0=$(date +%s)
  if "$PY" scripts/remote_docker.py --host "$PBT_DOCKER_CONTEXT" -- run --rm \
      -v xf_rust_mutation_repo:/repo -v xf_sccache:/sccache \
      -e RUSTC_WRAPPER=sccache -e SCCACHE_DIR=/sccache \
      -e PROPTEST_CASES="$PROPTEST_CASES" -e PBT_REMAINING="$(_remaining)" \
      -e PBT_PKGS="$pkg_flags" -w //repo/rust \
      "$RUST_IMAGE" sh -lc 'timeout "$PBT_REMAINING" cargo nextest run $PBT_PKGS -E "test(/prop_/)"'; then
    echo "[run-pbt] Rust PBT passed in $(( $(date +%s) - t0 ))s."
  else
    rust_rc=$?; echo "[run-pbt] Rust PBT FAILED (rc=$rust_rc) in $(( $(date +%s) - t0 ))s." >&2
    rc=$rust_rc
  fi
fi

exit "$rc"
