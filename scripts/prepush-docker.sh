#!/usr/bin/env bash
# Push-time quality gate — runs the Dell-only parallel quality orchestrator.
#
# Every per-language runner (run-python-quality.sh, run-python-repo-mutation.sh,
# run-rust-quality.sh, run-angular-quality.sh) self-syncs to the Dell helper and
# runs its heavy work THERE, fail-closed. scripts/run-scoped-static-quality.ps1
# fans them out in parallel so a push runs all quality on Dell at once. Local
# pre-commit uses the fast scope-gated precommit-docker.sh instead.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Prefer PowerShell 7 (pwsh); fall back to Windows PowerShell.
psh="pwsh"
command -v pwsh >/dev/null 2>&1 || psh="powershell.exe"

exec "$psh" -NoProfile -ExecutionPolicy Bypass -File scripts/run-scoped-static-quality.ps1
