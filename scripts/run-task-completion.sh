#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "TASK COMPLETION: quality-debt report"
timeout_seconds="${QUALITY_DEBT_TIMEOUT_SECONDS:-600}"
timeout --signal=TERM --kill-after=30 "$timeout_seconds" \
  python scripts/quality_debt_score.py --changed --debt-only \
    --evidence-out backend/reports/quality-evidence/quality-debt.jsonl
