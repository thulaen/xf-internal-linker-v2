#!/usr/bin/env bash
# Verify Slice 20 sidecar images are prebuilt and digest-pinned.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCKFILE="${XF_SIDECAR_IMAGE_LOCKFILE:-$ROOT/sidecar-images.lock.json}"

python3 - "$LOCKFILE" <<'PY'
import json
import re
import sys
from pathlib import Path

lockfile = Path(sys.argv[1])
payload = json.loads(lockfile.read_text(encoding="utf-8"))
required = ("streamd", "startupd", "sidecars")
digest_pattern = re.compile(r"^[^:@/]+(?::[0-9]+)?/.+@sha256:[0-9a-f]{64}$")
errors = []
for name in required:
    value = str(payload.get(name, "")).strip()
    if not value:
        errors.append(f"{name} image digest is missing")
    elif not digest_pattern.match(value):
        errors.append(f"{name} image must be registry/path@sha256:<64 lowercase hex>")
if errors:
    for error in errors:
        print(f"FAIL: {error}")
    print("[SIDECAR IMAGES READY: no]")
    sys.exit(1)
print("[SIDECAR IMAGES READY: yes]")
PY
