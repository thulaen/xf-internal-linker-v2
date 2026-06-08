#!/usr/bin/env bash
# dell-rust.sh — run a cargo command against the rust/ workspace ON THE DELL helper.
#
# MSI (Windows) carries weight 0.0 for builds/tests under the fail-closed routing
# in config/mutation-routing.json, and its compiled-tools image was removed to
# reclaim disk. ALL Rust compile / test / clippy / mutation / coverage therefore
# runs on Dell. This thin wrapper syncs the rust/ source tree into the Dell
# `xf_dell_compiled_repo` volume (build output excluded) and runs the given cargo
# command inside Dell's xf-linker-compiled-tools image, reusing the shared
# compiled_artifacts store and the persistent cargo/llvm cache volume.
#
# Usage (run on the Windows host, from anywhere in the repo):
#   bash scripts/dell-rust.sh build -p counting_bloom
#   bash scripts/dell-rust.sh test  -p counting_bloom
#   bash scripts/dell-rust.sh clippy -p counting_bloom -- -D warnings
#   bash scripts/dell-rust.sh fmt --check
#   bash scripts/dell-rust.sh mutants -p counting_bloom --jobs 6 --timeout 60
#   XF_DELL_RUST_NO_SYNC=1 bash scripts/dell-rust.sh test -p counting_bloom   # reuse last sync
#
# MSYS_NO_PATHCONV=1 is required: this runs under Git Bash on Windows, whose path
# converter would otherwise mangle the Docker volume/context arguments.
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd "$script_dir/.." && pwd)}"
cd "$repo_root"

if [[ "$#" -eq 0 ]]; then
  echo "[dell-rust] usage: dell-rust.sh <cargo-args...>   e.g. dell-rust.sh test -p counting_bloom" >&2
  exit 2
fi

DELL_VOLUME="xf_dell_compiled_repo"
DELL_CACHE_VOLUME="xf_dell_compiled_cache"
DELL_ARTIFACTS_VOLUME="compiled_artifacts"
DELL_IMAGE="xf-linker-compiled-tools:latest"

# Fail-closed: a missing Dell context/engine is a hard error, never a local fallback.
if ! docker --context dell version >/dev/null 2>&1; then
  echo "FAIL dell-rust: the Dell helper is unreachable." >&2
  echo "WHY: builds/tests run 100% on Dell (Windows weight 0.0, fail-closed). MSI has no compiled-tools image." >&2
  echo "UNBLOCK: start Docker Desktop on the Dell machine, then retry." >&2
  exit 3
fi

docker --context dell volume create "$DELL_VOLUME" >/dev/null 2>&1 || true
docker --context dell volume create "$DELL_CACHE_VOLUME" >/dev/null 2>&1 || true
docker --context dell volume create "$DELL_ARTIFACTS_VOLUME" >/dev/null 2>&1 || true

# Self-limiting timeouts so a hung REMOTE Docker stream never freezes the caller.
# The tar|docker-run-i sync and the cargo stream run over the remote Dell context and
# can intermittently hang on large/slow streams (docs K8S.26 wall-7: large stdin over
# `docker run -i` corrupts/hangs). Without an inner timeout a hung stream blocks the
# agent indefinitely; with it, the command self-kills and the caller gets a clean
# non-zero exit it can retry or report. `timeout` is GNU coreutils from Git Bash.
SYNC_TIMEOUT="${XF_DELL_SYNC_TIMEOUT:-240}"
CARGO_TIMEOUT="${XF_DELL_CARGO_TIMEOUT:-600}"
# Use GNU timeout by FULL PATH: bare `timeout` resolves to Windows timeout.exe first
# (different args), so we must call /usr/bin/timeout explicitly. Fall back to no-timeout
# only if the GNU binary is genuinely absent.
if [[ -x /usr/bin/timeout ]]; then TO() { /usr/bin/timeout -k 15 "$@"; }; else TO() { shift; "$@"; }; fi

# Sync-skip optimization: the FRAGILE part is the `docker run -i` stream to Dell, and the
# agent runs fmt+clippy+test back-to-back on identical source. Fingerprint rust/ LOCALLY
# (cheap tar|sha1sum) and skip the REMOTE sync when nothing changed since the last
# successful sync — cutting stream exposure ~3x per kernel. XF_DELL_RUST_NO_SYNC=1 forces
# skip; XF_DELL_FORCE_SYNC=1 forces a sync (use if the Dell volume was wiped). Per-volume
# state under TMPDIR.
RUST_TAR_EXCLUDES=(--exclude='rust/target' --exclude='rust/**/target' --exclude='rust/mutants.out' --exclude='rust/mutants.out.old')
sha1=/usr/bin/sha1sum; [[ -x "$sha1" ]] || sha1=sha1sum
sync_state="${TMPDIR:-/tmp}/.xf-dell-rust-sync.$(printf '%s' "$DELL_VOLUME" | "$sha1" | cut -c1-12)"

rust_fp=""
do_sync=1
if [[ "${XF_DELL_RUST_NO_SYNC:-0}" == "1" ]]; then
  do_sync=0
  echo "[dell-rust] XF_DELL_RUST_NO_SYNC=1 — reusing the last Dell sync."
else
  rust_fp="$(tar "${RUST_TAR_EXCLUDES[@]}" -cf - rust 2>/dev/null | "$sha1" | cut -c1-40)"
  if [[ "${XF_DELL_FORCE_SYNC:-0}" != "1" && -n "$rust_fp" && "$rust_fp" == "$(cat "$sync_state" 2>/dev/null)" ]]; then
    do_sync=0
    echo "[dell-rust] rust/ unchanged since last sync (fp ${rust_fp:0:12}) — skipping remote sync."
  fi
fi

if [[ "$do_sync" == "1" ]]; then
  echo "[dell-rust] syncing rust/ -> Dell volume ${DELL_VOLUME} (build output excluded; timeout ${SYNC_TIMEOUT}s)..."
  set +e
  tar "${RUST_TAR_EXCLUDES[@]}" -cf - rust | \
    TO "$SYNC_TIMEOUT" docker --context dell run --rm -i -v "${DELL_VOLUME}:/repo" alpine \
      sh -c "rm -rf /repo/rust && mkdir -p /repo && tar -xf - -C /repo"
  sync_rc=${PIPESTATUS[1]}
  set -e
  if [[ "$sync_rc" -ne 0 ]]; then
    if [[ "$sync_rc" -eq 124 ]]; then
      echo "FAIL dell-rust: Dell sync TIMED OUT after ${SYNC_TIMEOUT}s (the tar|docker-run-i stream hung)." >&2
    else
      echo "FAIL dell-rust: Dell sync failed (exit ${sync_rc})." >&2
    fi
    echo "UNBLOCK: retry once; if it keeps timing out the Dell stream is the problem — report 'blocked: Dell sync hang'." >&2
    exit 4
  fi
  [[ -n "$rust_fp" ]] && printf '%s' "$rust_fp" > "$sync_state" 2>/dev/null || true
fi

echo "[dell-rust] cargo $* (in /repo/rust on Dell; timeout ${CARGO_TIMEOUT}s)"
set +e
TO "$CARGO_TIMEOUT" docker --context dell run --rm \
  -v "${DELL_VOLUME}:/repo" \
  -v "${DELL_ARTIFACTS_VOLUME}:/opt/xf/compiled" \
  -v "${DELL_CACHE_VOLUME}:/root/.cache" \
  "$DELL_IMAGE" \
  bash -lc "cd /repo/rust && cargo $*"
cargo_rc=$?
set -e
[[ "$cargo_rc" -eq 124 ]] && echo "FAIL dell-rust: cargo $* TIMED OUT after ${CARGO_TIMEOUT}s on Dell (hung stream or test)." >&2
exit "$cargo_rc"
