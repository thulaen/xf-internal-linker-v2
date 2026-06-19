#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"
export MSYS_NO_PATHCONV=1

if [[ "${XF_BAZEL_PRIVATE_MUTATION:-0}" != "1" ]]; then
  echo "Bazel is the required quality path; run python scripts/bazel_default.py run //tools/quality:mutation." >&2
  exit 2
fi

explicit_paths=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --paths)
      explicit_paths="${2:-}"
      shift 2
      ;;
    *)
      echo "repo-mutmut:bad-argument"
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

python_cmd=(python)
if ! command -v "${python_cmd[0]}" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    python_cmd=(python3)
  elif command -v python.exe >/dev/null 2>&1; then
    python_cmd=(python.exe)
  elif command -v py >/dev/null 2>&1; then
    python_cmd=(py -3)
  else
    echo "repo-mutmut:python-missing"
    echo "Python is required to calculate the changed-file scope."
    exit 1
  fi
fi

mutation_context="${PYTHON_REPO_MUTATION_DOCKER_CONTEXT:-${PYTHON_MUTATION_DOCKER_CONTEXT:-dell}}"
docker_context_args=()
if [[ "$mutation_context" != "__local__" && "$mutation_context" != "local" ]]; then
  docker_context_args=(--context "$mutation_context")
fi

docker_cmd=(docker)
if ! "${docker_cmd[@]}" "${docker_context_args[@]}" version >/dev/null 2>&1; then
  if command -v docker.exe >/dev/null 2>&1; then
    docker_cmd=(docker.exe)
  elif [[ -x "/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]]; then
    docker_cmd=("/c/Program Files/Docker/Docker/resources/bin/docker.exe")
  else
    echo "repo-mutmut:docker-missing"
    echo "Docker is required to run compulsory Dell mutation tests."
    exit 1
  fi
fi

COMMIT_SCOPE_MODE="${COMMIT_SCOPE_MODE:-staged}"
scope_mode="$COMMIT_SCOPE_MODE"
image="xf-linker-backend-mutation-tools:latest"
scripts_regex='^scripts/.*\.py$'
githooks_regex='^\.githooks/.*\.py$'
: "${COMMIT_SCOPE_PATHS:=}"

paths="$(
  if [[ -n "$explicit_paths" ]]; then
    printf "%s\n" "$explicit_paths"
  elif [[ -n "${COMMIT_SCOPE_PATHS:-}" ]]; then
    printf "%s\n" "$COMMIT_SCOPE_PATHS"
  else
    "${python_cmd[@]}" scripts/commit_scope.py paths --mode "$scope_mode"
  fi \
    | grep -E "(${scripts_regex}|${githooks_regex})" \
    || true
)"
existing_paths=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$(basename "$path")" in
    test_*.py|tests_*.py) continue ;;
  esac
  if [[ -f "$path" ]]; then
    existing_paths="${existing_paths}${path}"$'\n'
  fi
done <<< "$paths"
paths="$(printf "%s" "$existing_paths" | sort -u)"

if [[ -z "$paths" ]]; then
  echo "repo-mutmut:no-changed-targets"
  exit 0
fi

pairs_file="$repo_root/audit/mutmut-repo-pairs.txt"
mkdir -p "$(dirname "$pairs_file")"
rm -f "$pairs_file"
test_targets=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  parent="$(dirname "$path")"
  stem="$(basename "$path" .py)"
  test_target="${XF_MUTMUT_TESTS:-}"
  if [[ -z "$test_target" ]]; then
    for candidate in "$parent/test_${stem}.py" "$parent/tests_${stem}.py"; do
      [[ -f "$candidate" ]] || continue
      test_target="$candidate"
      break
    done
  fi
  [[ -n "$test_target" ]] || continue
  printf "%s\t%s\n" "$path" "$test_target" >> "$pairs_file"
  test_targets="${test_targets}${test_target}"$'\n'
done <<< "$paths"

if [[ ! -s "$pairs_file" ]]; then
  echo "repo-mutmut:no-changed-targets"
  exit 0
fi

paths="$("${python_cmd[@]}" scripts/quality_cache.py filter-pairs --tool mutmut-repo --pairs-file "$pairs_file" | awk '{print $1}')"
test_targets="$(printf "%s" "$test_targets" | sort -u)"

if [[ -z "$paths" || -z "$test_targets" ]]; then
  echo "repo-mutmut:no-changed-targets (all cached)"
  exit 0
fi



echo "repo-mutmut:dell-required"

tmp_dir="/tmp/xf-mutmut-repo-scope"
mutmut_children="${XF_MUTMUT_CHILDREN:-}"
if [[ -z "$mutmut_children" && -n "${XF_QUALITY_CORES:-}" ]]; then
  mutmut_children="$XF_QUALITY_CORES"
fi
if [[ -z "$mutmut_children" ]]; then
  if ! mutmut_children="$(
    "${docker_cmd[@]}" "${docker_context_args[@]}" run --rm "$image" python -c 'import os; print(max(1, os.cpu_count() or 1))'
  )"; then
    echo "repo-mutmut:tool-missing"
    echo "Dell cannot run $image, so Python mutation cannot run."
    echo "Build it with: ssh dell docker compose --profile quality build backend-mutation-tools"
    exit 1
  fi
fi
changed_paths_json="$("${python_cmd[@]}" -c 'import json, sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))' <<< "$paths")"
test_targets_json="$("${python_cmd[@]}" -c 'import json, sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))' <<< "$test_targets")"
retry_scope_hash="$("${python_cmd[@]}" -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' <<< "${paths}${test_targets}")"

quality_docker_compose_run() {
  local label="$1"
  local service="$2"
  shift 2
  "${docker_cmd[@]}" "${docker_context_args[@]}" run --rm -i \
    -v xf_test_repo:/repo \
    -v xf_dell_quality_cache:/tmp/xf-test-cache \
    -w /repo \
    -e "MUTMUT_CHANGED_JSON=$changed_paths_json" \
    -e "MUTMUT_TESTS_JSON=$test_targets_json" \
    -e "MUTMUT_SCOPE_HASH=$retry_scope_hash" \
    -e "MUTMUT_TMP_DIR=$tmp_dir" \
    -e "MUTMUT_CHILDREN=$mutmut_children" \
    --name "xf_${label}_$$" \
    "$image" "$@"
}

"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm -i \
  -v xf_test_repo:/repo \
  alpine:latest sh -c "mkdir -p /repo/audit && find /repo -mindepth 1 -maxdepth 1 ! -name audit -exec rm -rf {} + && tar -xf - -C /repo && chmod 777 /repo/audit" \
  < <(tar -cf - scripts .githooks tools/quality config/mutation-routing.json .bazelrc audit/mutmut-repo-pairs.txt)

quality_docker_compose_run python-repo-mutation backend-mutation-tools bash -s <<'MUTMUT_REPO_SCRIPT'
set -euo pipefail
tmp_dir="${MUTMUT_TMP_DIR:-/tmp/xf-mutmut-repo-scope}"
rm -rf "$tmp_dir"
mkdir -p "$tmp_dir"
cd /repo
python - <<'PY'
import json
import os
import pathlib

tmp_dir = pathlib.Path(os.environ["MUTMUT_TMP_DIR"])
changed = json.loads(os.environ["MUTMUT_CHANGED_JSON"])
tests = json.loads(os.environ["MUTMUT_TESTS_JSON"])
runner = "python -m pytest -q " + " ".join(tests)
tmp_dir.joinpath("pyproject.toml").write_text(
    "[tool.mutmut]\n"
    + "paths_to_mutate = " + json.dumps(changed) + "\n"
    + "runner = " + json.dumps(runner) + "\n"
    + "tests_dir = " + json.dumps(tests) + "\n"
    + 'also_copy = ["scripts/", ".githooks/", "tools/quality/", "config/", ".bazelrc"]\n',
    encoding="utf-8",
)
PY
cp -R scripts "$tmp_dir/scripts"
cp -R .githooks "$tmp_dir/.githooks"
cp -R config "$tmp_dir/config"
cp .bazelrc "$tmp_dir/.bazelrc"
mkdir -p "$tmp_dir/tools"
cp -R tools/quality "$tmp_dir/tools/quality"
cd "$tmp_dir"
retry_file=/repo/audit/mutmut-repo-retry.txt
mutmut_args=()
retry_scope_line=
if [ -s "$retry_file" ]; then
  IFS= read -r retry_scope_line < "$retry_file" || retry_scope_line=
fi
if [ "$retry_scope_line" = "# scope $MUTMUT_SCOPE_HASH" ]; then
  mapfile -t mutmut_args < <(tail -n +2 "$retry_file" | sed 's/:$//; /^[[:space:]]*$/d')
  echo "repo-mutmut:retrying-failed-or-untested count=${#mutmut_args[@]}"
fi
set +e
mutmut run --max-children "$MUTMUT_CHILDREN" "${mutmut_args[@]}"
mutmut_status=$?
set -e
echo "repo-mutmut:run-status=$mutmut_status"
results_file="$tmp_dir/mutmut-results.txt"
mutmut results > "$results_file" || true
cat "$results_file"
if ! grep -Eiq ':[[:space:]]+(survived|no tests)$' "$results_file"; then
  rm -f "$retry_file"
  python /repo/scripts/quality_cache.py record-pairs --tool mutmut-repo --pairs-file /repo/audit/mutmut-repo-pairs.txt --root /repo || true
  exit 0
fi
{
  echo "# scope $MUTMUT_SCOPE_HASH"
  awk '/:[[:space:]]+(survived|no tests)$/ {name=$1; sub(/:$/, "", name); print name}' "$results_file"
} > "$retry_file"
exit 1
MUTMUT_REPO_SCRIPT
