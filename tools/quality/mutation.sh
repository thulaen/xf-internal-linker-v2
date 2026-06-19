#!/usr/bin/env bash
set -euo pipefail
repo_root_arg=""
if [[ "${1:-}" == --repo-root=* ]]; then
  repo_root_arg="${1#--repo-root=}"
  shift
fi

is_mutation_repo_root() {
  local candidate="$1"
  [[ -d "$candidate" ]] || return 1
  [[ -f "$candidate/tools/quality/mutation.sh" ]] || return 1
}

repo_root_candidates=()
[[ -n "$repo_root_arg" ]] && repo_root_candidates+=("$repo_root_arg")
[[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" ]] && repo_root_candidates+=("$BUILD_WORKSPACE_DIRECTORY")
[[ -n "${REPO_ROOT:-}" ]] && repo_root_candidates+=("$REPO_ROOT")
if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  repo_root_candidates+=("$git_root")
fi
repo_root=""
for candidate in "${repo_root_candidates[@]}"; do
  if is_mutation_repo_root "$candidate"; then
    repo_root="$candidate"
    break
  fi
done
if [[ -z "$repo_root" ]]; then
  echo "FAIL mutation: could not find the repo root for the Bazel mutation target." >&2
  echo "WHY: no runtime repo root argument, REPO_ROOT, or Git checkout contained tools/quality/mutation.sh." >&2
  echo "UNBLOCK: run through scripts/bazel_default.py so the repo root is exported." >&2
  exit 1
fi
cd "$repo_root"
export REPO_ROOT="$repo_root"
export BUILD_WORKSPACE_DIRECTORY="$repo_root"

echo "[mutation] Docker-backed mutation runners are retired."
echo "[mutation] The Bazel mutation target is now Docker-free and does not start old containers."
echo "[mutation] Requested args: ${*:-<none>}"
echo "[mutation] Active Docker-free quality command: python scripts/bazel_default.py test //tools/quality:all"
echo "[mutation] Full mutation needs a new Docker-free runner before it can be enforced again."
