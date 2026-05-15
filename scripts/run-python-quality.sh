#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path python)"
evidence_container="$(quality_evidence_container_path python)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT

mapfile -t changed_python < <(
  {
    git diff --cached --name-only --diff-filter=ACM
    git diff --name-only --diff-filter=ACM HEAD
    git ls-files --others --exclude-standard
  } | sort -u | grep -E "^backend/(apps|config)/.*\.py$" || true
)

if [[ "${#changed_python[@]}" -eq 0 ]]; then
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
  git diff --cached --name-only --diff-filter=ACM
  git diff --name-only --diff-filter=ACM HEAD
  git ls-files --others --exclude-standard
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

docker compose run --rm -T \
  -e QUALITY_PYTHON_TARGETS="$python_targets" \
  -e QUALITY_PYTHON_TEST_TARGETS="$python_test_targets" \
  -e QUALITY_PYTHON_BANDIT_TARGETS="$bandit_targets" \
  -e QUALITY_PYTHON_DEPENDENCY_CHANGED="$dependency_changed" \
  -e QUALITY_PYTHON_MUTATION_TARGETS="$mutation_targets" \
  -e QUALITY_PYTHON_MUTATION_TEST_TARGETS="$mutation_test_targets" \
  backend sh -lc '
  set -eu
  export DJANGO_SETTINGS_MODULE=config.settings.test
  export DJANGO_SECRET_KEY=ci-fake-secret-key
  evidence=/repo/backend/reports/quality-evidence/python.jsonl
  cd /repo/backend
  targets="$QUALITY_PYTHON_TARGETS"
  test_targets="$QUALITY_PYTHON_TEST_TARGETS"
  bandit_targets="${QUALITY_PYTHON_BANDIT_TARGETS:-}"
  dependency_changed="${QUALITY_PYTHON_DEPENDENCY_CHANGED:-0}"
  mutation_targets="$(printf "%s" "${QUALITY_PYTHON_MUTATION_TARGETS:-}" | tr "\n" " ")"
  mutation_test_targets="$(printf "%s" "${QUALITY_PYTHON_MUTATION_TEST_TARGETS:-}" | tr "\n" " ")"
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name ruff --command "ruff check $targets" --pass-summary "Ruff static check passed for changed backend files." --fail-summary "Ruff static check failed for changed backend files."
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type static_analysis --tool-name pylint --command "pylint --errors-only --disable=no-member $targets" --pass-summary "PyLint error-only check passed for changed backend files." --fail-summary "PyLint error-only check failed for changed backend files."
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
  if test "$dependency_changed" = "1"; then
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name pip-audit --command "pip-audit" --pass-summary "Python dependency audit passed." --fail-summary "Python dependency audit failed."
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name safety --command "safety check --full-report" --pass-summary "Safety dependency check passed." --fail-summary "Safety dependency check failed."
  else
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name pip-audit --command "pip-audit" --pass-summary "Python dependency audit passed." --fail-summary "Python dependency audit found existing dependency debt." || true
    python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type security --tool-name safety --command "safety check --full-report" --pass-summary "Safety dependency check passed." --fail-summary "Safety found existing dependency debt." || true
  fi
  python /repo/scripts/run_quality_step.py --evidence-out "$evidence" --check-type normal_test --tool-name pytest --command "cd /repo/backend && python -m pytest -p randomly -q --maxfail=1 --reuse-db --no-cov $test_targets" --pass-summary "Changed backend pytest targets passed." --fail-summary "Changed backend pytest targets failed."
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
  mutmut run --max-children 2 > reports/mutmut-run.txt 2>&1
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
  test "$mutmut_status" -eq 0
  test "$results_status" -eq 0
  test "$report_status" -eq 0
  test "$mutation_status" = "passed"
'
