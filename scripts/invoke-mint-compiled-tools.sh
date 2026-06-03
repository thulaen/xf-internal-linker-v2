#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash scripts/invoke-mint-compiled-tools.sh <command inside compiled-tools>" >&2
  exit 2
fi

mint_host="${MINT_HOST:-mint}"
mint_repo_path="${MINT_REPO_PATH:-/home/mint-helper-01/xf-internal-linker-v2}"
remote_command="$*"

quote_for_bash() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

env_args=""
if [[ -n "${QUALITY_GO_PATHS:-}" ]]; then
  env_args+=" -e QUALITY_GO_PATHS=$(quote_for_bash "$QUALITY_GO_PATHS")"
fi
if [[ -n "${QUALITY_CPP_CHANGED_FILES:-}" ]]; then
  env_args+=" -e QUALITY_CPP_CHANGED_FILES=$(quote_for_bash "$QUALITY_CPP_CHANGED_FILES")"
fi
if [[ -n "${XF_QUALITY_ENV:-}" ]]; then
  env_args+=" -e XF_QUALITY_ENV=$(quote_for_bash "$XF_QUALITY_ENV")"
fi

repo_q="$(quote_for_bash "$mint_repo_path")"
cmd_q="$(quote_for_bash "$remote_command")"

ssh "$mint_host" "
  set -e
  cd $repo_q
  docker inspect -f '{{.State.Running}}' xf_linker_compiled_tools 2>/dev/null | grep -q true || {
    echo 'Mint compiled-tools is not running. From Windows run: powershell -ExecutionPolicy Bypass -File scripts/start-mint-quality-tools.ps1' >&2
    exit 1
  }
  docker exec$env_args xf_linker_compiled_tools bash -lc $cmd_q
"
