#!/usr/bin/env bash
# Push the current working tree to the Mint helper's checkout so compiled-language
# quality (Rust/Go/Haskell/C++) builds the CURRENT code, not Mint's stale copy.
#
# Why tar-over-ssh and not rsync: rsync is not installed on the Windows host, and
# PowerShell corrupts binary pipes — so the orchestrator calls this through
# git-bash, which streams the tarball over ssh correctly. This is a source
# snapshot, not a whole-tree copy: generated outputs and permission-heavy local
# folders stay on Windows, while Mint receives only files Git knows about or new
# unignored working-tree source files.
#
# Env (with defaults matching scripts/run-scoped-static-quality.ps1):
#   MINT_USER       ssh user on Mint                (default: mint-helper-01)
#   MINT_HOST       ssh host/alias for Mint         (default: mint)
#   MINT_REPO_PATH  Mint's repo checkout path        (default: /home/mint-helper-01/xf-internal-linker-v2)
#   REPO_ROOT       local repo root to sync from     (default: derived from this script's location)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINT_USER="${MINT_USER:-mint-helper-01}"
MINT_HOST="${MINT_HOST:-mint}"
MINT_REPO_PATH="${MINT_REPO_PATH:-/home/mint-helper-01/xf-internal-linker-v2}"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Single source of truth for the synced file list (derives from git, respects
# .gitignore). Shared with run-dell-quality-shard.sh so the two can never drift
# apart. Callers cd to REPO_ROOT before invoking sync_file_list.
# shellcheck source=lib/sync_source_list.sh
. "${SCRIPT_DIR}/lib/sync_source_list.sh"

REMOTE_REPO_PATH_QUOTED="$(shell_quote "${MINT_REPO_PATH}")"
REMOTE_EXTRACT_COMMAND="set -euo pipefail; repo=${REMOTE_REPO_PATH_QUOTED}; mkdir -p \"\$repo\"; docker run --rm -v \"\$repo:/repo\" alpine sh -c 'find /repo -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +'; tar -xzf - -C \"\$repo\""

echo "[sync-tree-to-mint] ${REPO_ROOT} -> ${MINT_USER}@${MINT_HOST}:${MINT_REPO_PATH}"
( cd "${REPO_ROOT}" && sync_file_list ) |
  (cd "${REPO_ROOT}" && tar --null -T - -czf -) |
  ssh "${MINT_USER}@${MINT_HOST}" "${REMOTE_EXTRACT_COMMAND}"
echo "[sync-tree-to-mint] done"
