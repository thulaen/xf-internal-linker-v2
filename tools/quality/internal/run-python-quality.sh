#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

if [[ -f /.dockerenv ]]; then
  git config --global --add safe.directory /repo 2>/dev/null || true
fi
repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

if [[ "${XF_BAZEL_INTERNAL:-0}" != "1" ]]; then
  exec "${PYTHON_CMD:-python3}" scripts/bazel_default.py run //tools/quality:python -- "$@"
fi

# Phase H: shared concurrency + 5-min cap + named-container cleanup.
# Per the local test resource policy: every quality tool runs
# sequentially, with a 5-min wall-clock cap. The cleanup trap force-
# removes the docker container on EXIT/INT/TERM so orphans cannot
# survive a TaskStop or Ctrl-C.
. scripts/_quality_concurrency.sh
. scripts/_dell_only_guard.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock python-quality
wrapper_name="tools/quality/internal/run-python-quality.sh"
MAX_SCOPE_FILES_pytest=50

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path python)"
evidence_container="$(quality_evidence_container_path python)"
quality_evidence_init "$evidence_file"
_run_python_quality_combined_cleanup() {
  local rc=$?
  quality_evidence_finalize "$rc" "$evidence_file" "$evidence_container"
  quality_cleanup
  return "$rc"
}
trap _run_python_quality_combined_cleanup EXIT
trap '_run_python_quality_combined_cleanup; exit 130' INT
trap '_run_python_quality_combined_cleanup; exit 143' TERM

# Resolve python: the git-hook gate exposes `python`, but a stripped child PATH
# may not — fall back to python3 then known Windows locations so the runner is
# portable across shells.
PY="python"
if ! command -v "$PY" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  else
    for _c in "/c/Program Files/Python312/python.exe" "/c/Program Files/Python311/python.exe" "$repo_root/.venv/Scripts/python.exe"; do
      [[ -x "$_c" ]] && { PY="$_c"; break; }
    done
  fi
fi
export PYTHON_CMD="$PY"

mapfile -t changed_python < <(
  "$PY" scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}" |
    grep -E "^backend/(apps|config)/.*\.py$" |
    # generated sidecar protobuf stubs are covered by the shared contract test.
    grep -Ev "^backend/apps/_sidecars_pb/.+_pb2(_grpc)?\.py$" || true
)


if [[ "${#changed_python[@]}" -eq 0 ]]; then
  quality_log_scope_skip "$wrapper_name" pytest "$MAX_SCOPE_FILES_pytest"
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type normal_test \
    --status passed \
    --tool-name python-quality \
    --command "bash tools/quality/internal/run-python-quality.sh" \
    --summary "No changed backend Python file needed scoped Python quality checks." \
    --failure-fingerprint "python-quality:no-changed-targets"
  exit 0
fi

python_targets="$(
  printf "%s\n" "${changed_python[@]}" | sed "s#^backend/##" | tr -d "\r" | tr "\n" " "
)"
coverage_targets="$(
  printf "%s\n" "${changed_python[@]}" |
    grep -Ev "/(tests?|migrations)/|(^|/)test.*\.py$|(^|/)tests.*\.py$|_test\.py$" |
    sed "s#^backend/##" | tr -d "\r" | tr "\n" " " || true
)"
# Mutation logic lives in the Bazel-owned mutation target.
bandit_targets="$(
  printf "%s\n" "${changed_python[@]}" |
    grep -Ev "/(tests?|migrations)/|(^|/)test.*\.py$|(^|/)tests.*\.py$|_test\.py$" |
    sed "s#^backend/##" | tr -d "\r" | tr "\n" " " || true
)"
dependency_changed=0
if {
  "$PY" scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}"
} | grep -Eq "^backend/requirements(-dev)?\.txt$"; then
  dependency_changed=1
fi
target_dir="$repo_root/backend/reports/quality-targets"
mkdir -p "$target_dir"
test_target_map_file="$target_dir/python-test-target-map.json"
test_target_file="$(mktemp)"
test_target_error="$(mktemp)"
if ! "$PY" scripts/select_python_test_targets.py \
  --repo-root "$repo_root" \
  --map-out "$test_target_map_file" \
  "${changed_python[@]}" > "$test_target_file" 2> "$test_target_error"; then
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type normal_test \
    --status failed \
    --tool-name pytest-target-selector \
    --command "python scripts/select_python_test_targets.py changed backend files" \
    --summary "One or more changed backend files has no nearby pytest target." \
    --failure-fingerprint "pytest-target-selector:missing-target" \
    --raw-report-file "$test_target_error"
  exit 1
fi
python_test_targets="$(tr -d "\r" < "$test_target_file" | tr "\n" " ")"

python_targets_file="$target_dir/python-targets.txt"
python_test_targets_file="$target_dir/python-test-targets.txt"
coverage_targets_file="$target_dir/python-coverage-targets.txt"
bandit_targets_file="$target_dir/python-bandit-targets.txt"
printf "%s" "$python_targets" > "$python_targets_file"
printf "%s" "$python_test_targets" > "$python_test_targets_file"
printf "%s" "$coverage_targets" > "$coverage_targets_file"
printf "%s" "$bandit_targets" > "$bandit_targets_file"

# ── Default-on for local commits: shard lint + pytest to Dell, host-side ──
# The split runners dispatch over SSH to Dell from the host — never from inside
# backend-quality. An enabled split runs HERE and
# each tool's merged pass/fail is recorded as the SAME QualityEvidence row the
# in-container step writes (the runners take --evidence-out). When BOTH splits
# ran, the local backend-quality container is not started at all — Dell covered
# lint, types, security, pytest, coverage, and the dependency audit. CI
# (XF_QUALITY_ENV=ci) has no Dell context and keeps the in-container path.
host_evidence="$repo_root/backend/reports/quality-evidence/python.jsonl"
mkdir -p "$(dirname "$host_evidence")"
lint_split_done=0
pytest_split_done=0
# Route lint + pytest to the Dell helper for LOCAL commits — the turbo-quality
# rule runs 100% of Python quality on Dell. CI (XF_QUALITY_ENV=ci) keeps running
# them inside the CI container because the CI runner has no Dell docker context.
# machine_routing is fail-CLOSED: if Dell is unreachable the split raises and
# this gate hard-fails with a "fix Dell" message instead of silently linting on
# Windows. MSI ignores split-off overrides because it is an editing/control
# machine only.
if xf_on_msi_host; then
  # This Windows machine (MSI) never runs quality tools locally — force the
  # Dell splits no matter what XF_QUALITY_ENV / XF_*_SPLIT overrides say.
  XF_LINT_SPLIT=1
  XF_PYTEST_SPLIT=1
elif [[ "${XF_QUALITY_ENV:-local}" == "ci" ]]; then
  : "${XF_LINT_SPLIT:=0}"
  : "${XF_PYTEST_SPLIT:=0}"
else
  : "${XF_LINT_SPLIT:=1}"
  : "${XF_PYTEST_SPLIT:=1}"
fi
if [[ "${XF_LINT_SPLIT:-0}" == "1" ]]; then
  echo "[LINT SPLIT: routing ruff/mypy/bandit + dependency audit to Dell 100% (host-side)]"
  "$PY" "$repo_root/scripts/run_lint_on_context.py" \
    --files $python_targets --bandit-files $bandit_targets \
    --dependency-audit --evidence-out "$host_evidence"
  lint_split_rc=$?
  lint_split_done=1
  if [[ $lint_split_rc -ne 0 ]]; then exit $lint_split_rc; fi
fi
if [[ "${XF_PYTEST_SPLIT:-0}" == "1" ]]; then
  echo "[PYTEST SPLIT: routing pytest + coverage to Dell 100% (own test DB, host-side)]"
  cov_targets_csv="$(printf "%s" "$coverage_targets" | tr -s " " "," | sed "s/^,//;s/,$//")"
  pytest_split_args=(--targets $python_test_targets --evidence-out "$host_evidence")
  if [[ -f "$test_target_map_file" ]]; then
    pytest_split_args+=(--cache-map "$test_target_map_file")
  fi
  if [[ -n "$cov_targets_csv" ]]; then
    pytest_split_args+=(--cov-targets "$cov_targets_csv")
  fi
  "$PY" "$repo_root/scripts/run_pytest_on_context.py" "${pytest_split_args[@]}"
  pytest_split_rc=$?
  pytest_split_done=1
  if [[ $pytest_split_rc -ne 0 ]]; then exit $pytest_split_rc; fi
fi

if [[ "$lint_split_done" == "1" && "$pytest_split_done" == "1" ]]; then
  echo "[PYTHON QUALITY: all checks ran on Dell — lint, types, security, pytest, coverage, dependency audit. Local container not started.]"
  exit 0
fi

# Reaching this point means at least one split did not run — only CI runners
# may take the in-container path; the Windows host (MSI) is hard-blocked.
xf_block_local_quality_container run-python-quality
if [[ "${XF_QUALITY_ENV:-local}" != "ci" ]]; then
  echo "FAIL run-python-quality: the local container fallback is disabled outside CI." >&2
  echo "WHY: MSI is Docker-free; normal Python quality must run through Dell split runners." >&2
  echo "UNBLOCK: fix SSH access to Dell, then rerun the quality command." >&2
  exit 1
fi

# Phase H: stable container name + register for cleanup trap.
QUALITY_CONTAINER="$(quality_docker_container_name python-quality)"
quality_register_container "$QUALITY_CONTAINER"
docker_run_opts=()
if [[ "${XF_QUALITY_NO_BUILD:-0}" == "1" ]]; then
  docker_run_opts+=(--pull never)
fi
docker compose run --rm -T --name "$QUALITY_CONTAINER" "${docker_run_opts[@]}" \
  -e QUALITY_PYTHON_TARGETS_FILE="/repo/backend/reports/quality-targets/python-targets.txt" \
  -e QUALITY_PYTHON_TEST_TARGETS_FILE="/repo/backend/reports/quality-targets/python-test-targets.txt" \
  -e QUALITY_PYTHON_COVERAGE_TARGETS_FILE="/repo/backend/reports/quality-targets/python-coverage-targets.txt" \
  -e QUALITY_PYTHON_BANDIT_TARGETS_FILE="/repo/backend/reports/quality-targets/python-bandit-targets.txt" \
  -e QUALITY_PYTHON_DEPENDENCY_CHANGED="$dependency_changed" \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e XF_QUALITY_CORES="$(quality_cores)" \
  -e XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-0}" \
  -e SKIP_LINT_IN_CONTAINER="$lint_split_done" \
  -e SKIP_PYTEST_IN_CONTAINER="$pytest_split_done" \
  backend-quality sh -lc '
  set -eu
  export DJANGO_SETTINGS_MODULE=config.settings.test
  export DJANGO_SECRET_KEY=ci-fake-secret-key
  export XF_USE_POSTGRES_TEST_DB=1
  export XF_TEST_CACHE_ROOT="${XF_TEST_CACHE_ROOT:-/tmp/xf-test-cache}"
  export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$XF_TEST_CACHE_ROOT/xdg}"
  export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} --cache-dir=/tmp/xf-test-cache/pytest"
  export COVERAGE_FILE="${COVERAGE_FILE:-$XF_TEST_CACHE_ROOT/coverage/.coverage}"
  export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-$XF_TEST_CACHE_ROOT/mypy}"
  export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-$XF_TEST_CACHE_ROOT/ruff}"
  export MUTMUT_CACHE_DIR="${MUTMUT_CACHE_DIR:-$XF_TEST_CACHE_ROOT/mutmut}"
  mkdir -p "$XDG_CACHE_HOME" "$(dirname "$COVERAGE_FILE")" "$MYPY_CACHE_DIR" "$RUFF_CACHE_DIR" "$MUTMUT_CACHE_DIR" "$XF_TEST_CACHE_ROOT/pytest"
  evidence=/repo/backend/reports/quality-evidence/python.jsonl
  cd /repo/backend
  # Phase H in-container 5-min cap helper. CI runs uncapped via env.
  in_cap() {
    if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then "$@"; return $?; fi
    timeout --signal=TERM --kill-after=30 300 "$@"
  }
  read_target_file() {
    if [ -n "${1:-}" ] && [ -f "$1" ]; then
      tr -d "\r" < "$1" | tr "\n" " "
    fi
  }
  targets="$(read_target_file "${QUALITY_PYTHON_TARGETS_FILE:-}")"
  test_targets="$(read_target_file "${QUALITY_PYTHON_TEST_TARGETS_FILE:-}")"
  coverage_targets="$(read_target_file "${QUALITY_PYTHON_COVERAGE_TARGETS_FILE:-}")"
  bandit_targets="$(read_target_file "${QUALITY_PYTHON_BANDIT_TARGETS_FILE:-}")"
  dependency_changed="${QUALITY_PYTHON_DEPENDENCY_CHANGED:-0}"
  if [ "${SKIP_LINT_IN_CONTAINER:-0}" != "1" ]; then
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name ruff --command "ruff check $targets" --pass-summary "Ruff static check passed for changed backend files." --fail-summary "Ruff static check failed for changed backend files."
  # mypy type-checking — uses backend/mypy.ini so Django stubs + per-module
  # ignore_errors rules apply.  Running on the scoped $targets keeps it fast;
  # cross-module errors are suppressed by [mypy-apps.*] ignore_errors = True
  # until each module is brought into full type-check coverage incrementally.
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name mypy --command "python -m mypy --config-file /repo/backend/mypy.ini $targets" --pass-summary "mypy type-check passed for changed backend files." --fail-summary "mypy type-check failed for changed backend files."
  if test -n "$bandit_targets"; then
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name bandit --command "bandit -q $bandit_targets" --pass-summary "Bandit security check passed for changed backend application files." --fail-summary "Bandit security check failed for changed backend application files."
  else
    python /repo/scripts/write_quality_evidence.py \
      --out "$evidence" \
      --check-type security \
      --status passed \
      --tool-name bandit \
      --command "bandit changed backend application files" \
      --summary "No changed backend application file needed Bandit security scanning." \
      --failure-fingerprint "bandit:no-changed-targets"
  fi
  fi
  if test "$dependency_changed" = "1"; then
    # Slice 1.5 - even when requirements.txt is touched, surface pip-audit /
    # safety findings without aborting the commit. The existing 18 known
    # CVEs in django / nltk / setuptools / etc. predate slice 1.5 and are
    # tracked in paper-trail (resolved this session as #312 plus AutoIssue
    # #252). The structural fix is a dedicated CVE-upgrade slice, not this
    # tooling slice. Surfacing-only matches the else-branch behaviour.
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name pip-audit --command "pip-audit" --pass-summary "Python dependency audit passed." --fail-summary "Python dependency audit found existing dependency debt (tracked separately)." || true
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name safety --command "safety check --full-report" --pass-summary "Safety dependency check passed." --fail-summary "Safety found existing dependency debt (tracked separately)." || true
  else
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name pip-audit --command "pip-audit" --pass-summary "Python dependency audit passed." --fail-summary "Python dependency audit found existing dependency debt." || true
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name safety --command "safety check --full-report" --pass-summary "Safety dependency check passed." --fail-summary "Safety found existing dependency debt." || true
  fi
  coverage_args=""
  for target in $coverage_targets; do
    coverage_args="$coverage_args --cov=$target"
  done
  if test -z "$coverage_args"; then
    coverage_args="--no-cov"
  else
    coverage_args="$coverage_args --cov-report=json:/repo/backend/reports/coverage.json --cov-report=term"
  fi
  # 2026-05-19 — coverage is scoped to changed backend source files.
  # The old full-backend coverage command measured unrelated code and hid
  # the actual changed-file signal behind the full monolith.
  # Phase H: 5-min cap on pytest. Targets are already scoped to changed
  # backend files via select_python_test_targets.py.
  if [[ "${XF_TURBO_TESTS:-0}" == "1" ]]; then
    echo "[TURBO TESTS: distributing pytest shards via turbo_tests.py]"
    python /repo/scripts/turbo_tests.py --language python
    TURBO_RC=$?
    if [[ $TURBO_RC -ne 0 ]]; then exit $TURBO_RC; fi
    SKIP_LOCAL_PYTEST=1
  fi
  if [[ "${SKIP_LOCAL_PYTEST:-0}" != "1" && "${SKIP_PYTEST_IN_CONTAINER:-0}" != "1" ]]; then
    in_cap python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type normal_test --tool-name pytest --command "cd /repo/backend && python -m pytest --override-ini addopts= -p randomly -q --maxfail=1 --reuse-db $coverage_args $test_targets" --pass-summary "Changed backend pytest targets passed." --fail-summary "Changed backend pytest targets failed."
  fi
'
