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

. scripts/_quality_concurrency.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock python-mutation
wrapper_name="scripts/run-python-mutation.sh"
MAX_SCOPE_FILES_pytest=50

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path python)"
evidence_container="$(quality_evidence_container_path python)"
quality_evidence_init "$evidence_file"
_run_python_mutation_combined_cleanup() {
  local rc=$?
  quality_evidence_finalize "$rc" "$evidence_file" "$evidence_container"
  quality_cleanup
  return "$rc"
}
trap _run_python_mutation_combined_cleanup EXIT
trap '_run_python_mutation_combined_cleanup; exit 130' INT
trap '_run_python_mutation_combined_cleanup; exit 143' TERM

mapfile -t changed_python < <(
  python scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}" |
    grep -E "^backend/(apps|config)/.*\.py$" |
    grep -Ev "^backend/apps/_sidecars_pb/.+_pb2(_grpc)?\.py$" || true
)

if [[ "${#changed_python[@]}" -eq 0 ]]; then
  exit 0
fi

mutation_targets_raw="$(
  printf "%s\n" "${changed_python[@]}" |
    grep -Ev "/(tests?|migrations|management)/|(^|/)test.*\.py$|(^|/)tests.*\.py$|_test\.py$|(^|/)(apps|urls|__init__|models|admin|tasks(_[a-z0-9_]+)?|serializers|views|viewsets|forms|signals|signal_handlers|middleware|permissions|factories|conftest)\.py$|^backend/config/(settings/|wsgi|asgi|celery)" \
    || true
)"

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

pairs_file="/repo/audit/mutmut-pairs.txt"
rm -f "$pairs_file"
paste <(echo "$mutation_targets" | tr " " "\n") <(echo "$mutation_test_targets" | tr " " "\n") > "$pairs_file"
filtered_targets="$("${python_cmd[@]}" scripts/quality_cache.py filter-pairs --tool mutmut --pairs-file "$pairs_file" || true)"

if [[ -z "$filtered_targets" ]]; then
  echo "mutmut:no-changed-targets (all cached)"
  exit 0
fi

mutation_targets="$(echo "$filtered_targets" | awk '{print $1}' | tr "\n" " ")"
mutation_test_targets="$(echo "$filtered_targets" | awk '{print $2}' | tr "\n" " ")"

target_dir="$repo_root/backend/reports/quality-targets"
mkdir -p "$target_dir"
mutation_targets_file="$target_dir/python-mutation-targets.txt"
mutation_test_targets_file="$target_dir/python-mutation-test-targets.txt"
printf "%s" "$mutation_targets" > "$mutation_targets_file"
printf "%s" "$mutation_test_targets" > "$mutation_test_targets_file"

QUALITY_CONTAINER="$(quality_docker_container_name python-mutation)"
quality_register_container "$QUALITY_CONTAINER"
docker_run_opts=()
if [[ "${XF_QUALITY_NO_BUILD:-0}" == "1" ]]; then
  docker_run_opts+=(--pull never)
fi
docker compose run --rm -T --name "$QUALITY_CONTAINER" "${docker_run_opts[@]}" \
  -e QUALITY_PYTHON_MUTATION_TARGETS_FILE="/repo/backend/reports/quality-targets/python-mutation-targets.txt" \
  -e QUALITY_PYTHON_MUTATION_TEST_TARGETS_FILE="/repo/backend/reports/quality-targets/python-mutation-test-targets.txt" \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e XF_QUALITY_CORES="$(quality_cores)" \
  -e XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-0}" \
  backend-quality sh -lc '
  set -eu
  export XF_TEST_CACHE_ROOT="${XF_TEST_CACHE_ROOT:-/tmp/xf-test-cache}"
  export MUTMUT_CACHE_DIR="${MUTMUT_CACHE_DIR:-$XF_TEST_CACHE_ROOT/mutmut}"
  mkdir -p "$MUTMUT_CACHE_DIR"
  evidence=/repo/backend/reports/quality-evidence/python.jsonl
  cd /repo/backend
  
  read_target_file() {
    if [ -n "${1:-}" ] && [ -f "$1" ]; then
      tr -d "\r" < "$1" | tr "\n" " "
    fi
  }
  mutation_targets="$(read_target_file "${QUALITY_PYTHON_MUTATION_TARGETS_FILE:-}")"
  mutation_test_targets="$(read_target_file "${QUALITY_PYTHON_MUTATION_TEST_TARGETS_FILE:-}")"
  
  if [ "${XF_TURBO_MUTATION:-0}" = "1" ]; then
    echo "[run-python-mutation] XF_TURBO_MUTATION=1: mutation delegated to turbo coordinator"
    exit 0
  fi
  if test -z "$mutation_targets"; then
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
test_targets = [line for line in sys.argv[2].split() if line]
quoted = ", ".join(repr(path) for path in paths)
pytest_args = [
    "-p", "no:unraisableexception",
    "-p", "no:threadexception",
    "--override-ini", "addopts=",
    "-q", "--maxfail=5", "--reuse-db", "--no-cov",
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
  mutmut run --max-children "${XF_QUALITY_CORES:-2}" > reports/mutmut-run.txt 2>&1
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
        "survived", "no_tests", "suspicious", "timeout",
        "check_was_interrupted_by_user", "segfault",
    )
)
actual = 100.0 if total == 0 else ((killed + caught) / total) * 100.0
status = "passed" if blocking == 0 and actual == 100.0 else "failed"
print(f"mutation_status={status}")
print(f"mutation_actual={actual:.2f}")
PY
  . reports/mutmut-summary.env
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
  echo "$mutmut_status" > /tmp/xf-mutmut-scope/reports/mutmut-exit-status.txt
  if [ "$mutation_status" = "passed" ]; then
    python /repo/scripts/quality_cache.py record-pairs --tool mutmut --pairs-file /repo/audit/mutmut-pairs.txt --root /repo || true
  fi
  if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then
    test "$mutmut_status" -eq 0
    test "$results_status" -eq 0
    test "$report_status" -eq 0
    test "$mutation_status" = "passed"
  else
    true
  fi
'

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
