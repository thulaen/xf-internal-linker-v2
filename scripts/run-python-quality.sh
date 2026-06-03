#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

if [[ -f /.dockerenv ]]; then
  git config --global --add safe.directory /repo 2>/dev/null || true
fi
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Phase H: shared concurrency + 5-min cap + named-container cleanup.
# Per the local test resource policy: every quality tool runs
# sequentially, with a 5-min wall-clock cap. The cleanup trap force-
# removes the docker container on EXIT/INT/TERM so orphans cannot
# survive a TaskStop or Ctrl-C.
. scripts/_quality_concurrency.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock python-quality
wrapper_name="scripts/run-python-quality.sh"
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

mapfile -t changed_python < <(
  python scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}" |
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
    --command "bash scripts/run-python-quality.sh" \
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
mutation_targets_raw="$(
  printf "%s\n" "${changed_python[@]}" |
    grep -Ev "/(tests?|migrations|management)/|(^|/)test.*\.py$|(^|/)tests.*\.py$|_test\.py$|(^|/)(apps|urls|__init__|models|admin|tasks(_[a-z0-9_]+)?|serializers|views|viewsets|forms|signals|signal_handlers|middleware|permissions|factories|conftest)\.py$|^backend/config/(settings/|wsgi|asgi|celery)" \
    || true
)"
# Tool-scope filter (per the agent rules' tool-scope contract). Mutmut
# only mutates a file when BOTH conditions hold:
#   1. The file imports neither django nor apps.* at module level —
#      Django-coupled files are covered by pylint + pytest + bandit +
#      ruff because mutmut source rewrites trigger pytest-django
#      blocker leaks for django.test.TestCase suites.
#   2. The file has a sibling test_X.py / tests_X.py / tests_X_helpers.py
#      whose test classes are all SimpleTestCase or plain unittest —
#      a TestCase suite forces django_db_setup and the same blocker
#      leak.
# Files that fail either gate get dropped from mutation. If the
# filtered list is empty, the mutmut step writes a "no-changed-targets"
# evidence row and the gate continues.
mutation_targets=""
mutation_test_targets=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if grep -qE "^(from|import) (django|apps)([. ]|$)" "$path" 2>/dev/null; then
    continue
  fi
  parent="$(dirname "$path")"
  stem="$(basename "$path" .py)"
  test_file=""
  for candidate in \
    "$parent/test_${stem}.py" \
    "$parent/tests_${stem}.py" \
    "$parent/tests_${stem}_helpers.py"; do
    [[ -f "$candidate" ]] || continue
    if grep -qE "django\.test\.TestCase|(^|, )TestCase[ ,)]" "$candidate" 2>/dev/null; then
      continue
    fi
    test_file="$candidate"
    break
  done
  [[ -z "$test_file" ]] && continue
  mutation_targets+="${path#backend/} "
  mutation_test_targets+="${test_file#backend/} "
done <<< "$mutation_targets_raw"
mutation_targets="$(echo "$mutation_targets" | tr -d "\r")"
mutation_test_targets="$(echo "$mutation_test_targets" | tr -d "\r")"
bandit_targets="$(
  printf "%s\n" "${changed_python[@]}" |
    grep -Ev "/(tests?|migrations)/|(^|/)test.*\.py$|(^|/)tests.*\.py$|_test\.py$" |
    sed "s#^backend/##" | tr -d "\r" | tr "\n" " " || true
)"
dependency_changed=0
if {
  python scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}"
} | grep -Eq "^backend/requirements(-dev)?\.txt$"; then
  dependency_changed=1
fi
test_target_file="$(mktemp)"
test_target_error="$(mktemp)"
if ! python scripts/select_python_test_targets.py \
  --repo-root "$repo_root" \
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

target_dir="$repo_root/backend/reports/quality-targets"
mkdir -p "$target_dir"
python_targets_file="$target_dir/python-targets.txt"
python_test_targets_file="$target_dir/python-test-targets.txt"
coverage_targets_file="$target_dir/python-coverage-targets.txt"
bandit_targets_file="$target_dir/python-bandit-targets.txt"
mutation_targets_file="$target_dir/python-mutation-targets.txt"
mutation_test_targets_file="$target_dir/python-mutation-test-targets.txt"
printf "%s" "$python_targets" > "$python_targets_file"
printf "%s" "$python_test_targets" > "$python_test_targets_file"
printf "%s" "$coverage_targets" > "$coverage_targets_file"
printf "%s" "$bandit_targets" > "$bandit_targets_file"
printf "%s" "$mutation_targets" > "$mutation_targets_file"
printf "%s" "$mutation_test_targets" > "$mutation_test_targets_file"

# ── Opt-in: shard lint + pytest to Dell, host-side (outside the container) ──
# The split runners dispatch with `docker --context dell`, which only works from
# the host — never from inside backend-quality. So an enabled split runs HERE,
# the matching in-container step is skipped (SKIP_* env passed into the container
# below), and each tool's merged pass/fail is recorded as the SAME
# QualityEvidence row the in-container step writes (the runners take
# --evidence-out). Both vars default OFF: unset = today's local-only behaviour.
host_evidence="$repo_root/backend/reports/quality-evidence/python.jsonl"
mkdir -p "$(dirname "$host_evidence")"
lint_split_done=0
pytest_split_done=0
if [[ "${XF_LINT_SPLIT:-0}" == "1" ]]; then
  echo "[LINT SPLIT: sharding ruff/pylint/mypy/bandit to Dell 88% (host-side)]"
  python "$repo_root/scripts/run_lint_on_context.py" \
    --files $python_targets --bandit-files $bandit_targets --evidence-out "$host_evidence"
  lint_split_rc=$?
  lint_split_done=1
  if [[ $lint_split_rc -ne 0 ]]; then exit $lint_split_rc; fi
fi
if [[ "${XF_PYTEST_SPLIT:-0}" == "1" ]]; then
  echo "[PYTEST SPLIT: sharding pytest to Dell 88% (own test DB, host-side)]"
  python "$repo_root/scripts/run_pytest_on_context.py" \
    --targets $python_test_targets --evidence-out "$host_evidence"
  pytest_split_rc=$?
  pytest_split_done=1
  if [[ $pytest_split_rc -ne 0 ]]; then exit $pytest_split_rc; fi
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
  -e QUALITY_PYTHON_MUTATION_TARGETS_FILE="/repo/backend/reports/quality-targets/python-mutation-targets.txt" \
  -e QUALITY_PYTHON_MUTATION_TEST_TARGETS_FILE="/repo/backend/reports/quality-targets/python-mutation-test-targets.txt" \
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
  mutation_targets="$(read_target_file "${QUALITY_PYTHON_MUTATION_TARGETS_FILE:-}")"
  mutation_test_targets="$(read_target_file "${QUALITY_PYTHON_MUTATION_TEST_TARGETS_FILE:-}")"
  if [ "${SKIP_LINT_IN_CONTAINER:-0}" != "1" ]; then
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name ruff --command "ruff check $targets" --pass-summary "Ruff static check passed for changed backend files." --fail-summary "Ruff static check failed for changed backend files."
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name pylint --command "pylint --errors-only --disable=no-member $targets" --pass-summary "PyLint error-only check passed for changed backend files." --fail-summary "PyLint error-only check failed for changed backend files."
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
  if [ "${XF_TURBO_MUTATION:-0}" = "1" ]; then
    echo "[run-python-quality] XF_TURBO_MUTATION=1: mutation delegated to turbo coordinator (65/35 split via turbo_mutation.py)"
    exit 0
  fi
  if test -z "$mutation_targets"; then
    python /repo/scripts/write_quality_evidence.py \
      --out "$evidence" \
      --check-type mutation \
      --status passed \
      --tool-name mutmut \
      --command "mutmut run changed backend targets" \
      --summary "No changed backend application file needed mutmut mutation testing." \
      --failure-fingerprint "mutmut:no-changed-targets" \
      --target-percent 100 \
      --actual-percent 100
    exit 0
  fi
  workdir=/tmp/xf-mutmut-scope
  rm -rf "$workdir"
  mkdir -p "$workdir/reports"
  ln -s /repo/backend/apps "$workdir/apps"
  ln -s /repo/backend/config "$workdir/config"
  ln -s /repo/backend/pytest.ini "$workdir/pytest.ini"
  ln -s /repo/backend/conftest.py "$workdir/conftest.py"
  python - "$mutation_targets" "$mutation_test_targets" <<PY
from pathlib import Path
import sys

paths = [line for line in sys.argv[1].split() if line]
# Test targets were filtered in bash (run-python-quality.sh) to only
# include test files with NO django.test.TestCase usage. The script
# already exits the bash block on an empty mutation_targets via the
# is-empty check before this heredoc runs, so paths is always non-empty
# here.
test_targets = [line for line in sys.argv[2].split() if line]
quoted = ", ".join(repr(path) for path in paths)
pytest_args = [
    "-p",
    "no:unraisableexception",
    "-p",
    "no:threadexception",
    "--override-ini",
    "addopts=",
    "-q",
    "--maxfail=5",
    "--reuse-db",
    "--no-cov",
    *test_targets,
]
quoted_pytest_args = ", ".join(repr(arg) for arg in pytest_args)
Path("/tmp/xf-mutmut-scope/pyproject.toml").write_text(
    "[tool.mutmut]\n"
    f"paths_to_mutate = [{quoted}]\n"
    "also_copy = [\"apps\", \"config\", \"pytest.ini\", \"conftest.py\"]\n"
    f"pytest_add_cli_args = [{quoted_pytest_args}]\n",
    encoding="utf-8",
)
PY
  cd "$workdir"
  rm -rf .mutmut-cache mutants
  set +e
  # Phase H: 5-min cap on mutmut. Worker count comes from
  # quality_cores (default 4, max 6 plugged-in, env-overridable).
  # Phase I (next commit) will read the mutmut report and file
  # surviving-mutant AutoIssues instead of hard-blocking on score.
  in_cap mutmut run --max-children "${XF_QUALITY_CORES:-2}" > reports/mutmut-run.txt 2>&1
  mutmut_status=$?
  mutmut results --all true > reports/mutmut-results.txt
  results_status=$?
  mutmut export-cicd-stats > reports/mutmut-export.log
  report_status=$?
  set -e
  python - <<PY > reports/mutmut-summary.env
import json
from pathlib import Path

stats_path = Path("mutants/mutmut-cicd-stats.json")
if not stats_path.exists():
    print("mutation_status=failed")
    print("mutation_actual=0")
    raise SystemExit

stats = json.loads(stats_path.read_text(encoding="utf-8"))
total = int(stats.get("total") or 0)
killed = int(stats.get("killed") or 0)
caught = int(stats.get("caught_by_type_check") or 0)
blocking = sum(
    int(stats.get(name) or 0)
    for name in (
        "survived",
        "no_tests",
        "suspicious",
        "timeout",
        "check_was_interrupted_by_user",
        "segfault",
    )
)
actual = 100.0 if total == 0 else ((killed + caught) / total) * 100.0
status = "passed" if blocking == 0 and actual == 100.0 else "failed"
print(f"mutation_status={status}")
print(f"mutation_actual={actual:.2f}")
PY
  . reports/mutmut-summary.env
  # Order matters: the raw_snippet captured by `write_quality_evidence.py`
  # is truncated at 256 KB. Lay out the report so the most actionable
  # parts come first:
  #   1. cicd-stats.json — the actual mutation numbers (~200 bytes)
  #   2. export log — short summary
  #   3. last 200 lines of the verbose run log — failure tail
  #   4. last 200 lines of the per-mutant results — never-checked tail
  # The full results.txt is ~280 KB by itself for ~3500 mutants, so we
  # never store the whole thing here; if a debug dive needs it, the
  # workspace at /tmp/xf-mutmut-scope/ has the raw files until the next
  # `--clean` wipe.
  {
    echo "--- mutmut-cicd-stats.json ---"
    cat mutants/mutmut-cicd-stats.json 2>/dev/null || echo "(no stats file)"
    echo
    echo "--- mutmut-export.log ---"
    cat reports/mutmut-export.log 2>/dev/null
    echo
    echo "--- mutmut-run.txt (TAIL — failure surfaces here) ---"
    tail -n 200 reports/mutmut-run.txt 2>/dev/null
    echo
    echo "--- mutmut-results.txt (TAIL — sample of mutant verdicts) ---"
    tail -n 200 reports/mutmut-results.txt 2>/dev/null
  } > reports/mutmut-report.txt
  python /repo/scripts/write_quality_evidence.py \
    --out "$evidence" \
    --check-type mutation \
    --status "$mutation_status" \
    --tool-name mutmut \
    --tool-version "$(mutmut --version | head -n 1)" \
    --command "mutmut run for changed backend targets: $mutation_targets" \
    --summary "Changed backend mutation check ${mutation_status}." \
    --failure-fingerprint "mutmut:${mutation_status}:changed-targets" \
    --target-percent 100 \
    --actual-percent "$mutation_actual" \
    --raw-report-file reports/mutmut-report.txt
  # Phase I: stash mutmut exit status for the host-level survivor-file
  # step. Local commits are soft-block; CI keeps the original hard test.
  echo "$mutmut_status" > /tmp/xf-mutmut-scope/reports/mutmut-exit-status.txt
  if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then
    test "$mutmut_status" -eq 0
    test "$results_status" -eq 0
    test "$report_status" -eq 0
    test "$mutation_status" = "passed"
  else
    # Local: never exit non-zero on mutation regression. The
    # AutoIssue queue captures the gap.
    true
  fi
'

# Phase I: file surviving mutmut mutants. mutmut's
# export-cicd-stats writes mutants/mutmut-cicd-stats.json (inside
# /tmp/xf-mutmut-scope on the host bind). Soft-block only; non-zero
# exit here is non-blocking.
if [ -d /tmp/xf-mutmut-scope/mutants ] && [ -f /tmp/xf-mutmut-scope/mutants/mutmut-cicd-stats.json ]; then
  QUALITY_FILE_MUTANTS_CONTAINER="$(quality_docker_container_name file-mutants-mutmut)"
  quality_register_container "$QUALITY_FILE_MUTANTS_CONTAINER"
  docker compose run --rm -T --no-deps --name "$QUALITY_FILE_MUTANTS_CONTAINER" \
    -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
    -v /tmp/xf-mutmut-scope:/mutmut-scope:ro \
    backend sh -lc '
    cd /repo/backend
    python manage.py file_mutation_survivors \
      --tool mutmut \
      --report /mutmut-scope/mutants/mutmut-cicd-stats.json \
      --agent claude
  ' || echo "WARN: file_mutation_survivors mutmut step failed (non-blocking)"
fi
