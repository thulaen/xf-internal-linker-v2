#!/usr/bin/env bash
# Create a source snapshot without generated caches.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/tmp/source-snapshot.tar.gz}"
mkdir -p "$(dirname "$OUT")"
tar \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='node_modules' \
  --exclude='tmp' \
  -czf "$OUT" \
  -C "$ROOT" .
"$ROOT/scripts/lib/sha-tools.sh" >/dev/null
hash_value="$(bash -c "source '$ROOT/scripts/lib/sha-tools.sh'; sha256_file '$OUT'")"
echo "[SOURCE SNAPSHOT: path=$OUT sha256=$hash_value]"
