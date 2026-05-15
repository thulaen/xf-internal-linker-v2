#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"

quality_evidence_path() {
  local name="$1"
  echo "backend/reports/quality-evidence/${name}.jsonl"
}

quality_evidence_container_path() {
  local name="$1"
  echo "/repo/backend/reports/quality-evidence/${name}.jsonl"
}

quality_evidence_init() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  rm -f "$path"
}

quality_evidence_import() {
  local container_path="$1"
  docker compose run --rm -T backend \
    python manage.py ingest_quality_evidence \
      --path "$container_path" \
      --capture-raw-if-due
}

quality_artifact_prune() {
  docker compose run --rm -T backend \
    python manage.py prune_quality_artifacts \
      --root /tmp \
      --apply \
      --prune-old-raw-snippets
}

quality_evidence_finalize() {
  local status="$1"
  local host_path="$2"
  local container_path="$3"
  if [[ -s "$host_path" ]]; then
    if ! quality_evidence_import "$container_path"; then
      echo "Quality evidence import failed. Keeping full reports for inspection." >&2
      exit 1
    fi
    quality_artifact_prune
  fi
  exit "$status"
}

quality_evidence_write() {
  python scripts/write_quality_evidence.py "$@"
}

quality_artifact_safe_prune_host() {
  if command -v powershell >/dev/null 2>&1; then
    powershell -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1
    return
  fi
  if command -v pwsh >/dev/null 2>&1; then
    pwsh -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1
    return
  fi
  echo "PowerShell is unavailable; required verification-artifact pruning cannot run." >&2
  return 1
}
