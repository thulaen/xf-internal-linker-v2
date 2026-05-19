#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# shellcheck source=scripts/quality-evidence-lib.sh
. scripts/quality-evidence-lib.sh

quality_evidence_import() {
  echo "imported $1"
}

quality_artifact_prune() {
  echo "pruned"
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
evidence_file="$tmp_dir/evidence.jsonl"
stderr_file="$tmp_dir/stderr.txt"
printf '{"status":"failed"}\n' > "$evidence_file"

set +e
(
  quality_evidence_finalize 7 "$evidence_file" "/repo/backend/reports/quality-evidence/python.jsonl"
) 2>"$stderr_file" >"$tmp_dir/stdout.txt"
rc=$?
set -e

if [[ "$rc" -ne 7 ]]; then
  echo "expected quality_evidence_finalize to preserve status 7, got $rc" >&2
  exit 1
fi

if ! grep -q "Quality evidence finalized with failing status 7" "$stderr_file"; then
  echo "expected finalizer to explain the nonzero status" >&2
  cat "$stderr_file" >&2
  exit 1
fi

if ! grep -q "backend/reports/quality-evidence/python.jsonl" "$stderr_file"; then
  echo "expected finalizer to name the evidence file" >&2
  cat "$stderr_file" >&2
  exit 1
fi

echo "quality_evidence_finalize failure message test passed"
