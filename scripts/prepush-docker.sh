#!/usr/bin/env bash
# Push-time MUTATION gate — runs the Dell-only parallel mutation orchestrator.
#
# Every per-language mutation runner (run-python-mutation.sh,
# run-python-repo-mutation.sh, run-rust-mutation.sh, run-angular-mutation.sh)
# self-syncs to the Dell helper and runs its heavy work THERE, fail-closed.
# scripts/run-scoped-static-quality.ps1 fans them out in parallel so a push
# runs all mutation testing on Dell at once. Unit tests and lint run at
# pre-commit only, via the scope-gated precommit-docker.sh.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Prefer PowerShell 7 (pwsh); fall back to Windows PowerShell.
psh="pwsh"
command -v pwsh >/dev/null 2>&1 || psh="powershell.exe"

exec "$psh" -NoProfile -ExecutionPolicy Bypass -File scripts/run-scoped-static-quality.ps1
