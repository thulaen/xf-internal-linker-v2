#!/usr/bin/env bash
# Static proof for the source snapshot helper.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
grep -q -- "--exclude='.git'" "$ROOT/scripts/bundle-source.sh"
grep -q "sha256_file" "$ROOT/scripts/lib/sha-tools.sh"
echo "[SOURCE SNAPSHOT: static proof passed]"
