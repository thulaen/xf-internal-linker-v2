#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/_quality_concurrency.sh
. scripts/mutation_policy.sh
quality_install_cleanup_trap
quality_acquire_meta_lock
quality_acquire_tool_lock python-repo-mutation
mutation_args=()
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --mode)
      COMMIT_SCOPE_MODE="${2:-staged}"
      shift 2
      ;;
    *)
      mutation_args+=("$1")
      shift
      ;;
  esac
done
mutation_parse_args "${mutation_args[@]}"
mutation_refuse_full_in_hook

wrapper_name="scripts/run-python-repo-mutation.sh"
MAX_SCOPE_FILES_mutmut=20
mutmut_workers="$(quality_cores mutmut)"

mapfile -t scoped_python < <(
  if [[ -n "${COMMIT_SCOPE_PATHS:-}" ]]; then
    printf "%s\n" "$COMMIT_SCOPE_PATHS"
  else
    python scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}"
  fi |
    grep -E '^scripts/.*\.py$|^\.githooks/.*\.py$' |
    grep -Ev '(^|/)test_.*\.py$|(^|/)tests_.*\.py$|_test\.py$|__pycache__' |
    sort -u || true
)

mutation_targets=""
mutation_test_targets=""
for path in "${scoped_python[@]}"; do
  stem="$(basename "$path" .py)"
  safe_stem="${stem//-/_}"
  parent="$(dirname "$path")"
  candidates=(
    "$parent/test_${safe_stem}.py"
    "$parent/tests_${safe_stem}.py"
    "$parent/test_${stem}.py"
    "$parent/tests_${stem}.py"
    "scripts/test_${safe_stem}.py"
    ".githooks/test_${safe_stem}.py"
  )
  test_file=""
  for candidate in "${candidates[@]}"; do
    [[ -f "$candidate" ]] || continue
    test_file="$candidate"
    break
  done
  [[ -z "$test_file" ]] && continue
  if [[ "$test_file" == .githooks/* ]]; then
    test_file="tests/repo_githooks/$(basename "$test_file")"
  elif [[ "$test_file" == scripts/* ]]; then
    test_file="tests/repo_scripts/$(basename "$test_file")"
  fi
  mutation_targets+="$path "
  mutation_test_targets+="$test_file "
done

if [[ -z "$mutation_targets" ]]; then
  quality_log_scope_skip "$wrapper_name" mutmut "$MAX_SCOPE_FILES_mutmut"
  mkdir -p backend/reports/quality-evidence
  python scripts/write_quality_evidence.py \
    --out backend/reports/quality-evidence/python-repo-mutation.jsonl \
    --check-type mutation \
    --status passed \
    --tool-name mutmut \
    --command "mutmut run changed repo Python targets" \
    --summary "No changed repo-level Python file needed mutmut mutation testing." \
    --failure-fingerprint "repo-mutmut:no-changed-targets" \
    --target-percent 100 \
    --actual-percent 100
  exit 0
fi

if [[ "${XF_TURBO_MUTATION:-0}" == "1" ]]; then
  mkdir -p backend/reports/quality-evidence
  python scripts/write_quality_evidence.py \
    --out backend/reports/quality-evidence/python-repo-mutation.jsonl \
    --check-type mutation \
    --status passed \
    --tool-name mutmut \
    --command "mutmut run changed repo Python targets" \
    --summary "Repo-level Python mutation delegated to turbo coordinator." \
    --failure-fingerprint "repo-mutmut:delegated-to-turbo" \
    --target-percent 100 \
    --actual-percent 100
  echo "[run-python-repo-mutation] XF_TURBO_MUTATION=1: mutation delegated to turbo coordinator"
  exit 0
fi

quality_check_scope_cap "$wrapper_name" mutmut "$MAX_SCOPE_FILES_mutmut" "$mutation_targets"
mutation_log mutmut unknown "$mutmut_workers"
mkdir -p reports/mutation/local backend/reports/mutation/local

# mutmut lives in the `quality` Dockerfile stage (backend-quality), not the lean
# runtime `backend` service — run repo-level Python mutation there.
quality_docker_compose_run python-repo-mutation backend-quality \
  -e QUALITY_REPO_MUTATION_TARGETS="$mutation_targets" \
  -e QUALITY_REPO_MUTATION_TEST_TARGETS="$mutation_test_targets" \
  -e QUALITY_MUTMUT_WORKERS="$mutmut_workers" \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -- sh -lc '
  set -eu
  cd /repo
  workdir=/tmp/xf-mutmut-repo-scope
  rm -rf "$workdir"
  mkdir -p "$workdir/reports"
  for path in scripts .githooks docs; do
    if [ -e "/repo/$path" ]; then
      mkdir -p "$workdir/$(dirname "$path")"
      cp -R "/repo/$path" "$workdir/$path"
    fi
  done
  for path in AGENTS.md CLAUDE.md CODEX.md GEMINI.md PLAIN-ENGLISH-RULE.md; do
    cp "/repo/$path" "$workdir/$path" 2>/dev/null || true
  done
  for path in $QUALITY_REPO_MUTATION_TARGETS; do
    mkdir -p "$workdir/$(dirname "$path")"
    cp "/repo/$path" "$workdir/$path"
  done
  if echo "$QUALITY_REPO_MUTATION_TARGETS" | grep -q "\.githooks/"; then
    cp /repo/.githooks/_hook_helpers.py "$workdir/.githooks/_hook_helpers.py"
  fi
  for path in $QUALITY_REPO_MUTATION_TEST_TARGETS; do
    source_path="/repo/$path"
    if echo "$path" | grep -q "^tests/repo_githooks/"; then
      source_path="/repo/.githooks/$(basename "$path")"
    elif echo "$path" | grep -q "^tests/repo_scripts/"; then
      source_path="/repo/scripts/$(basename "$path")"
    fi
    mkdir -p "$workdir/$(dirname "$path")"
    cp "$source_path" "$workdir/$path"
    if echo "$path" | grep -q "^tests/repo_githooks/"; then
      python - "$workdir/$path" <<PY
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "HOOK_DIR = Path(__file__).resolve().parent",
    "HOOK_DIR = Path(__file__).resolve().parents[2] / \".githooks\"",
)
text = text.replace(
    "_HOOK_PATH = Path(__file__).resolve().parent / \"check-no-rwx.py\"",
    "_HOOK_PATH = Path(__file__).resolve().parents[2] / \".githooks\" / \"check-no-rwx.py\"",
)
path.write_text(text, encoding="utf-8")
PY
    elif echo "$path" | grep -q "^tests/repo_scripts/"; then
      python - "$workdir/$path" <<PY
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "HOOK_DIR = Path(__file__).resolve().parent",
    "HOOK_DIR = Path(__file__).resolve().parents[2] / \"scripts\"",
)
text = text.replace(
    "ROOT = Path(__file__).resolve().parents[1]",
    "ROOT = Path(__file__).resolve().parents[2]",
)
path.write_text(text, encoding="utf-8")
PY
    fi
  done
  cp /repo/pytest.ini "$workdir/pytest.ini" 2>/dev/null || true
  cd "$workdir"
  python - "$QUALITY_REPO_MUTATION_TARGETS" "$QUALITY_REPO_MUTATION_TEST_TARGETS" <<PY
from pathlib import Path
import sys

paths = [p for p in sys.argv[1].split() if p]
tests = [p for p in sys.argv[2].split() if p]
pytest_args = ["-q", "--maxfail=5", "--no-cov", *tests]
also_copy = [".githooks/_hook_helpers.py"]
Path("pyproject.toml").write_text(
    "[tool.mutmut]\n"
    "debug = true\n"
    f"paths_to_mutate = {[p for p in paths]!r}\n"
    f"also_copy = {also_copy!r}\n"
    f"pytest_add_cli_args = {pytest_args!r}\n",
    encoding="utf-8",
)
PY
  set +e
  mutmut run --max-children "${QUALITY_MUTMUT_WORKERS:-1}" > reports/mutmut-run.txt 2>&1
  mutmut_status=$?
  mutmut results --all true > reports/mutmut-results.txt 2>&1
  results_status=$?
  mutmut export-cicd-stats > reports/mutmut-export.log 2>&1
  report_status=$?
  set -e
  python - <<PY > reports/mutmut-summary.env
import json
from pathlib import Path

stats = json.loads(Path("mutants/mutmut-cicd-stats.json").read_text(encoding="utf-8"))
total = int(stats.get("total") or 0)
killed = int(stats.get("killed") or 0)
caught = int(stats.get("caught_by_type_check") or 0)
blocking = sum(int(stats.get(name) or 0) for name in ("survived", "no_tests", "suspicious", "timeout", "segfault"))
actual = 100.0 if total == 0 else ((killed + caught) / total) * 100.0
status = "passed" if blocking == 0 and actual == 100.0 else "failed"
print(f"mutation_status={status}")
print(f"mutation_actual={actual:.2f}")
PY
  . reports/mutmut-summary.env
  report_dir=/repo/reports/mutation/local
  if ! mkdir -p "$report_dir" 2>/dev/null; then
    report_dir=/repo/backend/reports/mutation/local
    mkdir -p "$report_dir"
  fi
  cp mutants/mutmut-cicd-stats.json "$report_dir/repo-python-mutmut.json"
  {
    echo "--- mutmut-cicd-stats.json ---"
    cat mutants/mutmut-cicd-stats.json
    echo "--- mutmut-run.txt tail ---"
    tail -n 200 reports/mutmut-run.txt
    echo "--- mutmut-results.txt tail ---"
    tail -n 200 reports/mutmut-results.txt
  } > reports/mutmut-report.txt
  python /repo/scripts/write_quality_evidence.py \
    --out /repo/backend/reports/quality-evidence/python-repo-mutation.jsonl \
    --check-type mutation \
    --status "$mutation_status" \
    --tool-name mutmut \
    --tool-version "$(mutmut --version | head -n 1)" \
    --command "mutmut run changed repo Python targets" \
    --summary "Changed repo-level Python mutation check ${mutation_status}." \
    --failure-fingerprint "repo-mutmut:${mutation_status}:changed-targets" \
    --target-percent 100 \
    --actual-percent "$mutation_actual" \
    --raw-report-file reports/mutmut-report.txt
  test "$mutmut_status" -eq 0
  test "$results_status" -eq 0
  test "$report_status" -eq 0
  test "$mutation_status" = "passed"
'
