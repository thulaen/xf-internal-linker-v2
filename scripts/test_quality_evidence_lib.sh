#!/usr/bin/env bash
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# shellcheck source=scripts/quality-evidence-lib.sh
. scripts/quality-evidence-lib.sh

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fake_backend="$tmp_dir/backend"
mkdir -p "$fake_backend"
cat > "$fake_backend/manage.py" <<'PY'
import os
import sys
from pathlib import Path

Path(os.environ["QUALITY_EVIDENCE_RECORD"]).write_text(
    " ".join(sys.argv[1:]),
    encoding="utf-8",
)
PY

export QUALITY_EVIDENCE_BACKEND_DIR="$fake_backend"
export QUALITY_EVIDENCE_FORCE_DIRECT=1
import_record="$tmp_dir/import-record.txt"
QUALITY_EVIDENCE_RECORD="$(cygpath -w "$import_record" 2>/dev/null || printf "%s" "$import_record")"
export QUALITY_EVIDENCE_RECORD
quality_evidence_import "/repo/backend/reports/quality-evidence/python.jsonl"
if ! grep -q "ingest_quality_evidence --path /repo/backend/reports/quality-evidence/python.jsonl --capture-raw-if-due" "$import_record"; then
  echo "expected direct container import to call manage.py ingest_quality_evidence" >&2
  cat "$import_record" >&2
  exit 1
fi

prune_record="$tmp_dir/prune-record.txt"
QUALITY_EVIDENCE_RECORD="$(cygpath -w "$prune_record" 2>/dev/null || printf "%s" "$prune_record")"
export QUALITY_EVIDENCE_RECORD
quality_artifact_prune
if ! grep -q "prune_quality_artifacts --root /tmp --apply --prune-old-raw-snippets" "$prune_record"; then
  echo "expected direct container prune to call manage.py prune_quality_artifacts" >&2
  cat "$prune_record" >&2
  exit 1
fi
unset QUALITY_EVIDENCE_FORCE_DIRECT

docker_record="$tmp_dir/docker-record.txt"
docker() {
  {
    printf "MSYS_NO_PATHCONV=%s\n" "${MSYS_NO_PATHCONV:-}"
    printf "MSYS2_ARG_CONV_EXCL=%s\n" "${MSYS2_ARG_CONV_EXCL:-}"
    printf "args=%s\n" "$*"
  } > "$docker_record"
}

(
  unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL
  quality_evidence_import "/repo/backend/reports/quality-evidence/python.jsonl"
)

if ! grep -q "MSYS_NO_PATHCONV=1" "$docker_record"; then
  echo "expected docker import to disable Git Bash path conversion" >&2
  cat "$docker_record" >&2
  exit 1
fi
if ! grep -q "MSYS2_ARG_CONV_EXCL=*" "$docker_record"; then
  echo "expected docker import to exclude all MSYS2 argument conversion" >&2
  cat "$docker_record" >&2
  exit 1
fi
unset -f docker

quality_evidence_import() {
  echo "imported $1"
}

quality_artifact_prune() {
  echo "pruned"
}

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
