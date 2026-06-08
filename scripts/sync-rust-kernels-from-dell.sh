#!/usr/bin/env bash
# sync-rust-kernels-from-dell.sh — the permanent Dell -> MSI Rust-kernel route.
#
# WHY THIS EXISTS
# ---------------
# MSI (this Windows host) RUNS the app but never BUILDS it: its Rust/C++ build
# images were removed to reclaim disk, and config/mutation-routing.json pins the
# Windows build/test weight to 0.0. Dell carries 100% of compiling. So when a
# kernel is ported to Rust ON DELL, its compiled `.so` has no automatic way to
# reach MSI's runtime store — the per-boot ensure_compiled_artifacts Rust path
# needs cargo (absent on MSI) and just skips. That is exactly how
# `anchor_self_information` went missing and crash-looped the backend.
#
# This script is that missing route. For each kernel name you pass it:
#   1. builds the kernel ON DELL    -> /usr/bin/bash scripts/dell-rust.sh build --release -p <k>
#   2. extracts lib<k>.so out of the Dell `xf_dell_compiled_repo` volume to .tmp/<k>.so
#   3. stages it into MSI's `xf-internal-linker-v2_compiled_artifacts` volume via a
#      one-off runtime container running scripts/_stage_prebuilt_rust_so.py, which
#      content-addresses the .so, links it as active/extensions/<k>.so, removes the
#      stale C++ <k>.cpython-*.so, and records it in the manifest so it PERSISTS
#      across reboots.
# After all kernels are staged it restarts the backend container so the boot-time
# ensure_compiled_artifacts import check sees the freshly staged kernels.
#
# USAGE (run on the Windows host, from anywhere in the repo, under Git Bash):
#   bash scripts/sync-rust-kernels-from-dell.sh anchor_self_information
#   bash scripts/sync-rust-kernels-from-dell.sh l2norm count_min_sketch counting_bloom
#   XF_SYNC_NO_BUILD=1 bash scripts/sync-rust-kernels-from-dell.sh <k>   # reuse last Dell build
#   XF_SYNC_NO_RESTART=1 bash scripts/sync-rust-kernels-from-dell.sh <k> # skip backend restart
#
# This is the canonical way every future Dell-built kernel reaches the MSI runtime.
#
# MSYS_NO_PATHCONV=1 is required throughout: under Git Bash on Windows the path
# converter would otherwise mangle the Docker volume/context/path arguments.
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# Self-limiting timeouts so a hung remote Docker stream / boot-looping restart never
# freezes the caller. GNU timeout by FULL PATH (bare `timeout` hits Windows timeout.exe).
if [[ -x /usr/bin/timeout ]]; then TO() { /usr/bin/timeout -k 15 "$@"; }; else TO() { shift; "$@"; }; fi
SO_PULL_TIMEOUT="${XF_SYNC_SO_PULL_TIMEOUT:-180}"
STAGE_TIMEOUT="${XF_SYNC_STAGE_TIMEOUT:-180}"
RESTART_TIMEOUT="${XF_SYNC_RESTART_TIMEOUT:-240}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd "$script_dir/.." && pwd)}"
cd "$repo_root"

if [[ "$#" -eq 0 ]]; then
  echo "[sync-rust] usage: sync-rust-kernels-from-dell.sh <kernel-name> [<kernel-name> ...]" >&2
  echo "[sync-rust]   e.g. sync-rust-kernels-from-dell.sh anchor_self_information" >&2
  exit 2
fi

DELL_VOLUME="xf_dell_compiled_repo"
MSI_ARTIFACTS_VOLUME="xf-internal-linker-v2_compiled_artifacts"
RUNTIME_IMAGE="${XF_RUNTIME_IMAGE:-xf-linker-backend-runtime:latest}"
TMP_DIR="$repo_root/.tmp"

mkdir -p "$TMP_DIR"

for kernel in "$@"; do
  echo ""
  echo "==================================================================="
  echo "[sync-rust] kernel: $kernel"
  echo "==================================================================="

  if [[ "${XF_SYNC_NO_BUILD:-0}" != "1" ]]; then
    echo "[sync-rust] 1/3 building on Dell ..."
    /usr/bin/bash "$script_dir/dell-rust.sh" build --release -p "$kernel"
  else
    echo "[sync-rust] 1/3 build skipped (XF_SYNC_NO_BUILD=1) — reusing last Dell build."
  fi

  echo "[sync-rust] 2/3 extracting lib$kernel.so from Dell volume -> $TMP_DIR/$kernel.so (timeout ${SO_PULL_TIMEOUT}s)"
  set +e
  TO "$SO_PULL_TIMEOUT" docker --context dell run --rm -v "${DELL_VOLUME}:/repo" alpine \
    cat "/repo/rust/target/release/lib${kernel}.so" > "$TMP_DIR/$kernel.so"
  pull_rc=$?
  set -e
  if [[ "$pull_rc" -eq 124 ]]; then
    echo "[sync-rust] FAIL: pulling lib$kernel.so from Dell TIMED OUT after ${SO_PULL_TIMEOUT}s (remote stream hung)." >&2
    exit 5
  fi
  if [[ ! -s "$TMP_DIR/$kernel.so" ]]; then
    echo "[sync-rust] FAIL: lib$kernel.so was empty or missing in the Dell volume." >&2
    echo "[sync-rust] UNBLOCK: run the Dell build first (drop XF_SYNC_NO_BUILD)." >&2
    exit 1
  fi

  echo "[sync-rust] 3/3 staging into MSI runtime store via one-off ROOT container (timeout ${STAGE_TIMEOUT}s) ..."
  # Run the stager as ROOT (--user 0): the active/extensions store is root-owned, so a
  # non-root stager hits PermissionError writing the active symlink — this exact failure
  # stalled prior agents. Root is correct here: only the stager writes the store; the
  # backend only ever reads it.
  set +e
  TO "$STAGE_TIMEOUT" docker run --rm --user 0 \
    -v "${MSI_ARTIFACTS_VOLUME}:/opt/xf/compiled" \
    -v "$repo_root:/repo" \
    -v "$TMP_DIR:/staged" \
    -e XF_COMPILED_ARTIFACT_ROOT=/opt/xf/compiled \
    -e PYTHONPATH=/repo/scripts \
    "$RUNTIME_IMAGE" \
    python /repo/scripts/_stage_prebuilt_rust_so.py --name "$kernel" --so "/staged/$kernel.so"
  stage_rc=$?
  set -e
  if [[ "$stage_rc" -ne 0 ]]; then
    [[ "$stage_rc" -eq 124 ]] && echo "[sync-rust] FAIL: staging $kernel TIMED OUT after ${STAGE_TIMEOUT}s." >&2 || echo "[sync-rust] FAIL: staging $kernel failed (exit ${stage_rc})." >&2
    exit 6
  fi
done

if [[ "${XF_SYNC_NO_RESTART:-0}" != "1" ]]; then
  echo ""
  echo "[sync-rust] restarting backend container so the boot import check picks up the kernels (timeout ${RESTART_TIMEOUT}s) ..."
  set +e
  TO "$RESTART_TIMEOUT" docker compose restart backend
  restart_rc=$?
  set -e
  if [[ "$restart_rc" -eq 124 ]]; then
    echo "[sync-rust] WARN: 'docker compose restart backend' TIMED OUT after ${RESTART_TIMEOUT}s — the backend may be boot-looping on the C++ fingerprint; refresh the manifest digest so boot skips the C++ rebuild." >&2
  fi
else
  echo "[sync-rust] backend restart skipped (XF_SYNC_NO_RESTART=1)."
fi

echo ""
echo "[sync-rust] done. Staged: $*"
