#!/usr/bin/env bash
# Prove the SLICE-21 go-live history-copy closeout is wired and non-destructive.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAP="$ROOT/k8s/obs/history-copy/volume-map.json"
COPY_SCRIPT="$ROOT/scripts/obs-history-copy.ps1"
LIB_SCRIPT="$ROOT/scripts/obs-history-lib.ps1"
RETIRE_SCRIPT="$ROOT/scripts/obs-retire-old-volumes.ps1"
RESTORE_JOB="$ROOT/k8s/obs/history-copy/restore-job.yaml"

python3 - "$MAP" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
volumes = data.get("volumes", [])
names = [entry.get("volume") for entry in volumes]
if len(names) != len(set(names)):
    raise SystemExit("FAIL: duplicate monitoring history volume in volume-map.json")
required = {"volume", "pvc", "mount", "node"}
for entry in volumes:
    missing = required - set(entry)
    if missing:
        raise SystemExit(f"FAIL: {entry!r} missing {sorted(missing)}")
print(f"PASS volume map covers {len(volumes)} file-backed monitoring volumes")
PY

require_text() {
  local file="$1"
  local needle="$2"
  if ! grep -Fq -- "$needle" "$file"; then
    echo "FAIL: $file does not contain required text: $needle" >&2
    exit 1
  fi
}

reject_text() {
  local file="$1"
  local needle="$2"
  if grep -Fq -- "$needle" "$file"; then
    echo "FAIL: $file contains forbidden text: $needle" >&2
    exit 1
  fi
}

require_text "$LIB_SCRIPT" "function Get-XfStagedSha256"
require_text "$LIB_SCRIPT" "ssh -o BatchMode=yes"
if grep -Fq -- "retired" "$COPY_SCRIPT"; then
  require_text "$COPY_SCRIPT" "Monitoring history copy from MSI Docker volumes is retired"
  require_text "$COPY_SCRIPT" "observability now runs in Kubernetes"
else
  require_text "$COPY_SCRIPT" "volume-map.json"
  require_text "$COPY_SCRIPT" "Get-FileHash -Algorithm SHA256"
  require_text "$COPY_SCRIPT" "MaxRetries"
  require_text "$COPY_SCRIPT" "Get-XfStagedSha256"
fi
require_text "$RETIRE_SCRIPT" "-ConfirmGoLiveComplete"
require_text "$RETIRE_SCRIPT" "Get-XfStagedSha256"
require_text "$RETIRE_SCRIPT" "retired_kept"
require_text "$RESTORE_JOB" "sha256sum"
require_text "$RESTORE_JOB" ".copy-complete"

for file in "$COPY_SCRIPT" "$RETIRE_SCRIPT" "$RESTORE_JOB"; do
  reject_text "$file" "docker volume rm" # protected-data-stores: documentation
  reject_text "$file" "docker volume prune" # protected-data-stores: documentation
done

echo "PASS SLICE-21 history-copy closeout is wired and keeps old volumes"
