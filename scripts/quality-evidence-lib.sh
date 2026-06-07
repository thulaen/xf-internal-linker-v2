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

quality_docker_run_opts() {
  if [[ "${XF_QUALITY_NO_BUILD:-0}" == "1" ]]; then
    printf "%s\n" "--pull" "never"
  fi
}

quality_evidence_acquire_import_lock() {
  local lock_dir="${QUALITY_LOCK_DIR:-/tmp/xf-quality-locks}"
  local lock_file="$lock_dir/quality-evidence-import.lock"
  mkdir -p "$lock_dir"
  if command -v flock >/dev/null 2>&1; then
    exec 200>"$lock_file"
    flock 200
    return
  fi
  while ! mkdir "$lock_file.d" 2>/dev/null; do
    sleep 1
  done
}

quality_evidence_release_import_lock() {
  local lock_dir="${QUALITY_LOCK_DIR:-/tmp/xf-quality-locks}"
  local lock_file="$lock_dir/quality-evidence-import.lock"
  if command -v flock >/dev/null 2>&1; then
    flock -u 200 2>/dev/null || true
    return
  fi
  rmdir "$lock_file.d" 2>/dev/null || true
}

quality_evidence_init() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  rm -f "$path"
}

quality_evidence_import() {
  local container_path="$1"
  if [[ "${QUALITY_EVIDENCE_SKIP_IMPORT:-0}" == "1" ]]; then
    echo "Quality evidence import skipped for this remote compute shard. Language checks still decide pass or fail." >&2
    return 0
  fi
  quality_evidence_acquire_import_lock
  if [[ "${QUALITY_EVIDENCE_FORCE_DIRECT:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
    local docker_run_opts=()
    mapfile -t docker_run_opts < <(quality_docker_run_opts)
    set +e
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose run \
      --rm -T "${docker_run_opts[@]}" backend \
      python manage.py ingest_quality_evidence \
        --path "$container_path" \
        --capture-raw-if-due
    local rc=$?
    set -e
    quality_evidence_release_import_lock
    return "$rc"
  fi
  local backend_dir="${QUALITY_EVIDENCE_BACKEND_DIR:-/repo/backend}"
  if [[ -f "$backend_dir/manage.py" ]]; then
    set +e
    (
      cd "$backend_dir"
      python manage.py ingest_quality_evidence \
      --path "$container_path" \
      --capture-raw-if-due
    )
    local rc=$?
    set -e
    quality_evidence_release_import_lock
    return "$rc"
  fi
  echo "Quality evidence import needs either Docker on PATH or ${backend_dir}/manage.py." >&2
  quality_evidence_release_import_lock
  return 127
}

quality_artifact_prune() {
  if [[ "${QUALITY_EVIDENCE_SKIP_IMPORT:-0}" == "1" ]]; then
    return 0
  fi
  quality_evidence_acquire_import_lock
  if [[ "${QUALITY_EVIDENCE_FORCE_DIRECT:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
    local docker_run_opts=()
    mapfile -t docker_run_opts < <(quality_docker_run_opts)
    set +e
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose run \
      --rm -T "${docker_run_opts[@]}" backend \
      python manage.py prune_quality_artifacts \
        --root /tmp \
        --apply \
        --prune-old-raw-snippets
    local rc=$?
    set -e
    quality_evidence_release_import_lock
    return "$rc"
  fi
  local backend_dir="${QUALITY_EVIDENCE_BACKEND_DIR:-/repo/backend}"
  if [[ -f "$backend_dir/manage.py" ]]; then
    set +e
    (
      cd "$backend_dir"
      python manage.py prune_quality_artifacts \
      --root /tmp \
      --apply \
      --prune-old-raw-snippets
    )
    local rc=$?
    set -e
    quality_evidence_release_import_lock
    return "$rc"
  fi
  echo "Quality artifact pruning needs either Docker on PATH or ${backend_dir}/manage.py." >&2
  quality_evidence_release_import_lock
  return 127
}

quality_evidence_finalize() {
  local status="$1"
  local host_path="$2"
  local container_path="$3"
  if [[ -s "$host_path" ]]; then
    if ! quality_evidence_import "$container_path"; then
      echo "Quality evidence import failed. Keeping full reports for inspection." >&2
      return 1
    fi
    rm -f "$host_path"
    quality_artifact_prune
  fi
  if [[ "$status" -ne 0 ]]; then
    echo "Quality evidence finalized with failing status $status. Evidence was imported from ${container_path#/repo/}; inspect the imported quality evidence or rerun the tool command named in that evidence row." >&2
  fi
  return "$status"
}

quality_evidence_write() {
  "${PYTHON:-python3}" scripts/write_quality_evidence.py "$@"
}

quality_artifact_safe_prune_host() {
  local rc=0
  if command -v powershell >/dev/null 2>&1; then
    powershell -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1 || rc=$?
  elif command -v pwsh >/dev/null 2>&1; then
    pwsh -ExecutionPolicy Bypass -File scripts/prune-verification-artifacts.ps1 || rc=$?
  else
    echo "PowerShell is unavailable; required verification-artifact pruning cannot run." >&2
    return 1
  fi

  # Paper-trail safe-prune extension. Only acts on directories whose
  # files reference paths from a *resolved* PaperTrailEntry whose
  # `resolution_lessons` is populated. Dry-run by default; the trace
  # output goes to stdout so the operator can review.
  if command -v docker >/dev/null 2>&1; then
    docker compose exec -T backend python -c "
from pathlib import Path
from apps.paper_trail.services.safe_prune import paper_trail_eligible_dirs
import tempfile
root = Path(tempfile.gettempdir())
for d in paper_trail_eligible_dirs(root):
    print(f'[paper-trail safe-prune candidate] {d}')
" 2>/dev/null || true
  fi

  return "$rc"
}
