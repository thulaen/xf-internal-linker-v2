#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export MSYS_NO_PATHCONV=1

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
if [[ "$mutation_context" != "__local__" ]]; then
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
    | grep -Ev '(^|/)(test_.*|tests_.*|.*_test)[.]py$' \
    || true
)"
existing_paths=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if [[ -f "$path" ]]; then
    existing_paths="${existing_paths}${path}"$'\n'
  fi
done <<< "$paths"
paths="$(printf "%s" "$existing_paths" | sort -u)"

if [[ -z "$paths" ]]; then
  echo "repo-mutmut:no-changed-targets"
  exit 0
fi

mkdir -p .tmp
pairs_file=".tmp/mutmut-repo-pairs.txt"
test_target="${XF_MUTMUT_TESTS:-}"
if [[ -z "$test_target" ]]; then
  test_target="scripts/test_python_repo_mutation.py"
  if grep -qx "scripts/bazel_default.py" <<< "$paths"; then
    test_target="$test_target scripts/test_bazel_default.py"
  fi
fi
rm -f "$pairs_file"
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  printf "%s\t%s\n" "$path" "$test_target" >> "$pairs_file"
done <<< "$paths"

paths="$("${python_cmd[@]}" scripts/quality_cache.py filter-pairs --tool mutmut-repo --pairs-file "$pairs_file" | awk '{print $1}')"

if [[ -z "$paths" ]]; then
  echo "repo-mutmut:no-changed-targets (all cached)"
  exit 0
fi



echo "repo-mutmut:dell-required"

tmp_dir="/tmp/xf-mutmut-repo-scope"
mutmut_children="${XF_MUTMUT_CHILDREN:-}"
if [[ -z "$mutmut_children" ]]; then
  if ! mutmut_children="$(
    "${docker_cmd[@]}" "${docker_context_args[@]}" run --rm "$image" python -c 'import os; print(max(2, min(16, os.cpu_count() or 2)))'
  )"; then
    echo "repo-mutmut:tool-missing"
    echo "Dell cannot run $image, so Python mutation cannot run."
    echo "Build it with: ssh dell docker compose --profile quality build backend-mutation-tools"
    exit 1
  fi
fi
changed_paths_json="$("${python_cmd[@]}" -c 'import json, sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))' <<< "$paths")"

quality_docker_compose_run() {
  local label="$1"
  local service="$2"
  shift 2
  "${docker_cmd[@]}" "${docker_context_args[@]}" run --rm \
    -v xf_test_repo:/repo \
    -v xf_dell_quality_cache:/tmp/xf-test-cache \
    -w /repo \
    --name "xf_${label}_$$" \
    "$image" "$@"
}

"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm -i \
  -v xf_test_repo:/repo \
  alpine:latest sh -c "rm -rf /repo/* && tar -xf - -C /repo && mkdir -p /repo/audit && chmod 777 /repo/audit" \
  < <(tar -cf - scripts .githooks tools/quality)

quality_docker_compose_run python-repo-mutation backend-mutation-tools bash -lc "
set -euo pipefail
rm -rf '$tmp_dir'
mkdir -p '$tmp_dir'
cd /repo
python - <<'PY'
import json
from pathlib import Path

changed_paths = $changed_paths_json
paths_to_mutate = changed_paths
test_target = '$test_target'
test_targets = test_target.split()
Path('$tmp_dir/pyproject.toml').write_text(
    '[tool.mutmut]\n'
    + 'paths_to_mutate = ' + json.dumps(paths_to_mutate) + '\n'
    + 'runner = ' + json.dumps(f'python -m pytest -q {test_target}') + '\n'
    + 'tests_dir = ' + json.dumps(test_targets) + '\n'
    + 'also_copy = [' + json.dumps('scripts/') + ', ' + json.dumps('.githooks/') + ', ' + json.dumps('tools/quality/') + ']\n',
    encoding='utf-8',
)
Path('/repo/audit/mutmut-repo-pairs.txt').write_text(
    ''.join(f'{path}\t{test_target}\n' for path in changed_paths),
    encoding='utf-8',
)
PY
cp -R scripts '$tmp_dir/scripts'
cp -R .githooks '$tmp_dir/.githooks'
mkdir -p '$tmp_dir/tools'
cp -R tools/quality '$tmp_dir/tools/quality'
cd '$tmp_dir'
mutmut run --max-children '$mutmut_children'
python - <<'PY'
import json
import subprocess
import sys

raw = subprocess.run(['mutmut', 'results'], text=True, capture_output=True, check=False)
text = raw.stdout + raw.stderr
survivors = [line for line in text.splitlines() if line.strip() and 'survived' in line.lower()]
killed = [line for line in text.splitlines() if line.strip() and 'killed' in line.lower()]
total = len(survivors) + len(killed)
kill_rate = 100.0 if total == 0 else (len(killed) / total) * 100.0
print(json.dumps({'kill_rate': round(kill_rate, 1), 'killed': len(killed), 'survived': len(survivors), 'survivors': survivors[:20]}))
# Repo target: >90% kill rate (not 100% — do not chase every last mutant).
if kill_rate >= 90.0:
    print('mutation passed')
    sys.exit(0)
sys.exit(1)
PY
python /repo/scripts/quality_cache.py record-pairs --tool mutmut-repo --pairs-file /repo/audit/mutmut-repo-pairs.txt --root /repo || true
"
