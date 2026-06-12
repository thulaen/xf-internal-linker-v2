#!/usr/bin/env bash
# Scoped Python (backend) mutation testing — Dell-only, fail-closed.
#
# mutmut runs ONLY on the Dell helper machine via `docker --context dell`
# inside xf-linker-backend-mutation-tools:latest. There is no Windows or
# local-container fallback: if Dell is unreachable this script fails
# closed (exit 1) and the push stops.
#
# Content-hash pair caching: every <source, sibling-test> pair is checked
# against scripts/quality_cache.py (tool=mutmut). Pairs whose file content
# is unchanged since their last PASSING run are skipped; passing pairs are
# recorded after the run so the next push skips them.
#
# Source sync uses the DEDICATED xf_python_mutation_repo volume — never
# xf_test_repo, which scripts/run-python-repo-mutation.sh wipes in
# parallel during the same push.
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
PYTHON_MUTATION_DOCKER_CONTEXT="${PYTHON_MUTATION_DOCKER_CONTEXT:-dell}"
PYTHON_MUTATION_VOLUME="xf_python_mutation_repo"
PYTHON_MUTATION_IMAGE="xf-linker-backend-mutation-tools:latest"

. scripts/_dell_only_guard.sh
xf_require_remote_context run-python-mutation "$PYTHON_MUTATION_DOCKER_CONTEXT"

python_cmd=(python)
if ! command -v "${python_cmd[0]}" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    python_cmd=(python3)
  elif command -v py >/dev/null 2>&1; then
    python_cmd=(py -3)
  else
    echo "FAIL run-python-mutation: python is not on PATH." >&2
    echo "WHY: the changed-file scope, the content-hash cache, and the kill-rate summary all run with host Python." >&2
    echo "UNBLOCK: install Python or fix PATH for this shell, then re-run git push." >&2
    exit 1
  fi
fi

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

write_mutation_evidence() {
  "${python_cmd[@]}" scripts/write_quality_evidence.py \
    --out "$evidence_file" \
    --check-type mutation \
    --tool-name mutmut \
    --target-percent 90 \
    "$@"
}

fail_three_part() {
  echo "FAIL run-python-mutation: $1" >&2
  echo "WHY: $2" >&2
  echo "UNBLOCK: $3" >&2
}

mapfile -t changed_python < <(
  "${python_cmd[@]}" scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}" |
    tr -d "\r" |
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

mkdir -p .tmp
pairs_file=".tmp/python-mutation-pairs.txt"
rm -f "$pairs_file"
pair_count=0
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
  printf "%s\t%s\n" "$path" "$test_file" >> "$pairs_file"
  pair_count=$((pair_count + 1))
done <<< "$mutation_targets_raw"

if [[ "$pair_count" -eq 0 ]]; then
  echo "[run-python-mutation] No mutation-eligible changed backend files -- skipping."
  exit 0
fi

to_run_pairs_file=".tmp/python-mutation-pairs-to-run.txt"
"${python_cmd[@]}" scripts/quality_cache.py filter-pairs --tool mutmut --pairs-file "$pairs_file" | tr -d "\r" > "$to_run_pairs_file"

if [[ ! -s "$to_run_pairs_file" ]]; then
  echo "[MUTATION CACHE: all $pair_count source/test pairs unchanged since last pass]"
  write_mutation_evidence \
    --status passed \
    --command "mutmut scoped run skipped via scripts/quality_cache.py filter-pairs (tool=mutmut)" \
    --summary "All $pair_count changed backend source/test pairs are content-unchanged since their last passing mutmut run, so the Dell mutation run was skipped (content-hash cache hit)."
  exit 0
fi

mutation_targets="$(awk '{print $1}' "$to_run_pairs_file" | sed 's|^backend/||' | tr '\n' ' ')"
mutation_test_targets="$(awk '{print $2}' "$to_run_pairs_file" | sed 's|^backend/||' | tr '\n' ' ')"

if ! docker --context "$PYTHON_MUTATION_DOCKER_CONTEXT" info >/dev/null 2>&1; then
  fail_three_part \
    "the Dell docker context is unreachable." \
    "all mutation testing runs on Dell only -- there is no Windows fallback." \
    "wake/fix the Dell machine and re-run git push."
  exit 1
fi

mapfile -t tar_excludes < <("${python_cmd[@]}" scripts/_sync_tar_excludes.py | tr -d "\r")
if ! tar -cf - "${tar_excludes[@]}" backend \
    | docker --context "$PYTHON_MUTATION_DOCKER_CONTEXT" run --rm -i \
        -v "$PYTHON_MUTATION_VOLUME":/repo \
        alpine:latest sh -c "rm -rf /repo/backend && tar -xf - -C /repo"; then
  fail_three_part \
    "the source sync to Dell failed." \
    "mutmut mutates the backend tree inside the $PYTHON_MUTATION_VOLUME volume on Dell; without a fresh sync it would test stale code." \
    "check 'docker --context dell info' and free disk space on Dell, then re-run git push."
  exit 1
fi

dell_log=".tmp/python-mutation-run.log"
stats_file=".tmp/python-mutation-stats.json"
rm -f "$dell_log" "$stats_file"
set +e
docker --context "$PYTHON_MUTATION_DOCKER_CONTEXT" run --rm \
  -v "$PYTHON_MUTATION_VOLUME":/repo \
  -v xf_dell_quality_cache:/tmp/xf-test-cache \
  -w /repo/backend \
  -e QUALITY_PYTHON_MUTATION_TARGETS="$mutation_targets" \
  -e QUALITY_PYTHON_MUTATION_TEST_TARGETS="$mutation_test_targets" \
  "$PYTHON_MUTATION_IMAGE" bash -lc '
  set -eu
  export XF_TEST_CACHE_ROOT="${XF_TEST_CACHE_ROOT:-/tmp/xf-test-cache}"
  export MUTMUT_CACHE_DIR="${MUTMUT_CACHE_DIR:-$XF_TEST_CACHE_ROOT/mutmut}"
  mkdir -p "$MUTMUT_CACHE_DIR"
  cd /repo/backend

  mutation_targets="${QUALITY_PYTHON_MUTATION_TARGETS:-}"
  mutation_test_targets="${QUALITY_PYTHON_MUTATION_TEST_TARGETS:-}"
  if test -z "$mutation_targets"; then
    exit 0
  fi
  mutmut_children="$(python -c "import os; print(max(2, min(16, os.cpu_count() or 2)))")"

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
  mutmut run --max-children "$mutmut_children" > reports/mutmut-run.txt 2>&1
  mutmut_status=$?
  mutmut results --all true > reports/mutmut-results.txt 2>&1
  mutmut export-cicd-stats > reports/mutmut-export.log 2>&1
  set -e
  echo "--- mutmut exit status: $mutmut_status ---"
  echo "--- mutmut version ---"
  mutmut --version 2>/dev/null | head -n 1 || true
  echo "--- mutmut-export.log ---"
  cat reports/mutmut-export.log 2>/dev/null || true
  echo "--- mutmut-run.txt (TAIL -- failure surfaces here) ---"
  tail -n 200 reports/mutmut-run.txt 2>/dev/null || true
  echo "--- mutmut-results.txt (TAIL -- sample of mutant verdicts) ---"
  tail -n 200 reports/mutmut-results.txt 2>/dev/null || true
  echo "XF_PYTHON_MUTATION_STATS_JSON_BEGIN"
  cat mutants/mutmut-cicd-stats.json 2>/dev/null || echo "{}"
' > "$dell_log" 2>&1
dell_status=$?
set -e

tail -n 60 "$dell_log" 2>/dev/null || true

if [[ "$dell_status" -ne 0 ]]; then
  write_mutation_evidence \
    --status failed \
    --command "docker --context $PYTHON_MUTATION_DOCKER_CONTEXT run $PYTHON_MUTATION_IMAGE mutmut run (targets: $mutation_targets)" \
    --summary "The Dell mutmut container exited with status $dell_status before producing stats." \
    --failure-fingerprint "mutmut:dell-run-failed" \
    --actual-percent 0 \
    --raw-report-file "$dell_log"
  fail_three_part \
    "the mutmut run on Dell exited with status $dell_status before producing stats." \
    "the container itself failed (missing image, broken tool, or Dell-side error), so no kill rate could be measured." \
    "read .tmp/python-mutation-run.log; if the image is missing, build it with: docker --context dell compose --profile quality build backend-mutation-tools, then re-run git push."
  exit 1
fi

awk 'found { print } /^XF_PYTHON_MUTATION_STATS_JSON_BEGIN/ { found=1 }' "$dell_log" | tr -d '\r' > "$stats_file"

summary_line="$("${python_cmd[@]}" - "$stats_file" <<'PY'
import json
import sys
from pathlib import Path

try:
    stats = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    stats = None
if not isinstance(stats, dict) or not stats:
    print("failed 0.00")
    raise SystemExit
total = int(stats.get("total") or 0)
killed = int(stats.get("killed") or 0)
caught = int(stats.get("caught_by_type_check") or 0)
actual = 100.0 if total == 0 else ((killed + caught) / total) * 100.0
# Gate: >= 90% kill rate (config/mutation-routing.json kill_rate_gates.python).
status = "passed" if actual >= 90.0 else "failed"
print(f"{status} {actual:.2f}")
PY
)"
summary_line="$(printf "%s" "$summary_line" | tr -d "\r")"
mutation_status="${summary_line%% *}"
mutation_actual="${summary_line##* }"

write_mutation_evidence \
  --status "$mutation_status" \
  --command "mutmut run on Dell ($PYTHON_MUTATION_IMAGE) for changed backend targets: $mutation_targets" \
  --summary "Changed backend mutation check ${mutation_status} on Dell: kill rate ${mutation_actual}% against the 90% gate." \
  --failure-fingerprint "mutmut:${mutation_status}:changed-targets" \
  --actual-percent "$mutation_actual" \
  --raw-report-file "$dell_log"

if [[ "$mutation_status" == "passed" ]]; then
  "${python_cmd[@]}" scripts/quality_cache.py record-pairs --tool mutmut --pairs-file "$to_run_pairs_file" || true
fi

if [[ -s "$stats_file" ]]; then
  QUALITY_FILE_MUTANTS_CONTAINER="$(quality_docker_container_name file-mutants-mutmut)"
  quality_register_container "$QUALITY_FILE_MUTANTS_CONTAINER"
  docker compose run --rm -T --no-deps --name "$QUALITY_FILE_MUTANTS_CONTAINER" \
    -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
    backend sh -lc '
    cd /repo/backend
    python manage.py file_mutation_survivors \
      --tool mutmut \
      --report /repo/.tmp/python-mutation-stats.json \
      --agent claude
  ' || echo "WARN: file_mutation_survivors mutmut step failed (non-blocking)"
fi

if [[ "$mutation_status" != "passed" ]]; then
  fail_three_part \
    "scoped mutmut kill rate ${mutation_actual}% is below the 90% gate." \
    "surviving mutants mean the paired tests do not detect real code changes; the gate is 90% per config/mutation-routing.json kill_rate_gates.python." \
    "read .tmp/python-mutation-run.log for the surviving mutants, strengthen the sibling tests, then re-run git push."
  exit 1
fi
echo "[run-python-mutation] passed: kill rate ${mutation_actual}% (gate 90%) on Dell."
