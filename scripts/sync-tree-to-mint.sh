#!/usr/bin/env bash
# Push the current working tree to the Mint helper's checkout so compiled-language
# quality (Rust/Go/Haskell/C++) builds the CURRENT code, not Mint's stale copy.
#
# Why tar-over-ssh and not rsync: rsync is not installed on the Windows host, and
# PowerShell corrupts binary pipes — so the orchestrator calls this through
# git-bash, which streams the tarball over ssh correctly. This is an *additive*
# sync (tar has no --delete); scoped quality runs tolerate leftover stale files.
# The k3s + Bazel path (RBE input upload + K8S.17 source snapshot) replaces this
# bridge once the cluster is live.
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

echo "[sync-tree-to-mint] ${REPO_ROOT} -> ${MINT_USER}@${MINT_HOST}:${MINT_REPO_PATH}"
tar -czf - \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='frontend/dist' \
  --exclude='backend/reports' \
  -C "${REPO_ROOT}" . \
  | ssh "${MINT_USER}@${MINT_HOST}" "mkdir -p '${MINT_REPO_PATH}' && tar -xzf - -C '${MINT_REPO_PATH}'"
echo "[sync-tree-to-mint] done"
