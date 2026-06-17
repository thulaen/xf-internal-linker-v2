#!/usr/bin/env bash
# Build + push the Bazel rules_oci runner images to the Mint registry, on the
# Dell build node (ADR 0010, KUBE PLAN SLICE-23).
#
# Run from the bazel workspace root ON DELL (the build + cache host):
#   bash tools/runners/push-runner-images.sh            # all known runners
#   bash tools/runners/push-runner-images.sh merge      # just one
#
# It prints each pushed "<repo>:<tag>: digest: sha256:..." line; copy the digest
# into runner-images.lock.json, then verify:
#   python3 tools/runners/verify_lockfile.py
#
# Images are built one at a time (Dell also runs the DB + tests; serialize so a
# build never starves them — ADR 0010). Pushed by digest; tags are pointers only.
set -euo pipefail

runners=("$@")
if [ "${#runners[@]}" -eq 0 ]; then
  runners=(merge python rust node-browser)
fi

for r in "${runners[@]}"; do
  echo "=== building //tools/runners/${r}:image ==="
  bazel build "//tools/runners/${r}:image"
  echo "=== pushing //tools/runners/${r}:push ==="
  bazel run "//tools/runners/${r}:push" 2>&1 \
    | grep -oE "xf-runner-${r}:[^ ]+: digest: sha256:[a-f0-9]+" | tail -1
done

echo "Done. Record the digest(s) above in runner-images.lock.json, then run:"
echo "  python3 tools/runners/verify_lockfile.py"
