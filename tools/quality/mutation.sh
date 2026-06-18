#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

repo_root="${BUILD_WORKSPACE_DIRECTORY:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root=*)
      repo_root="${1#--repo-root=}"
      shift
      ;;
    --repo-root)
      repo_root="${2:?--repo-root requires a path}"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

cd "${repo_root:-$(pwd)}"

repo_mutation_context="${PYTHON_REPO_MUTATION_DOCKER_CONTEXT:-dell}"
if command -v docker >/dev/null 2>&1 && ! docker --context "$repo_mutation_context" version >/dev/null 2>&1; then
  export PYTHON_REPO_MUTATION_DOCKER_CONTEXT="__local__"
fi

scope_paths="${COMMIT_SCOPE_PATHS:-}"
if [[ -z "$scope_paths" ]]; then
  bash scripts/run-python-mutation.sh "$@"
  bash scripts/run-python-repo-mutation.sh "$@"
  bash scripts/run-rust-mutation.sh "$@"
  bash scripts/run-angular-mutation.sh "$@"
  exit 0
fi

if grep -qE '^backend/(apps|config)/.*[.]py$' <<< "$scope_paths"; then
  bash scripts/run-python-mutation.sh "$@"
else
  echo "[mutation] No backend Python mutation scope -- skipping mutmut."
fi

if grep -qE '^(scripts|[.]githooks)/.*[.]py$' <<< "$scope_paths"; then
  bash scripts/run-python-repo-mutation.sh "$@"
else
  echo "[mutation] No script mutation scope -- skipping repo mutmut."
fi

if grep -qE '^(rust|services)/' <<< "$scope_paths"; then
  bash scripts/run-rust-mutation.sh "$@"
else
  echo "[mutation] No Rust mutation scope -- skipping cargo-mutants."
fi

if grep -qE '^frontend/.*[.](ts|js|html|scss|css)$' <<< "$scope_paths"; then
  bash scripts/run-angular-mutation.sh "$@"
else
  echo "[mutation] No frontend mutation scope -- skipping Stryker."
fi
