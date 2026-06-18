#!/usr/bin/env bash
# Copy one file into place through a same-directory temporary file.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: tools/atomic-upload.sh <source> <destination>" >&2
  exit 2
fi

source_path="$1"
dest_path="$2"
dest_dir="$(dirname "$dest_path")"
mkdir -p "$dest_dir"
tmp_path="${dest_path}.tmp.$$"
cp "$source_path" "$tmp_path"
mv "$tmp_path" "$dest_path"
echo "[ATOMIC UPLOAD: wrote $dest_path]"
