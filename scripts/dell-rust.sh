#!/usr/bin/env bash
# dell-rust.sh — run an arbitrary `cargo <args>` on the Dell helper.
#
# The Windows host (MSI) does not build/test/bench Rust locally (the
# compiled-tools image was removed and config/mutation-routing.json pins the
# Windows weight to 0). This is the ONE general-purpose Dell-cargo path that the
# block-msi-build-test guard points at. It mirrors the proven sync+run handshake
# in run-rust-quality.sh: tar the Rust workspace into a Dell-side named volume,
# then run cargo inside the compiled-tools image with sccache warm.
#
# Usage:
#   bash scripts/dell-rust.sh build -p scoring
#   bash scripts/dell-rust.sh nextest run -p texttok
#   bash scripts/dell-rust.sh bench  -p scoring        # Criterion benches
#
# Env:
#   DELL_RUST_CONTEXT   docker context to use (default: dell)
#   DELL_RUST_VOLUME    repo volume name      (default: xf_dell_rust)
#   DELL_RUST_WORKDIR   workdir inside /repo   (default: rust)
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

CTX="${DELL_RUST_CONTEXT:-dell}"
VOL="${DELL_RUST_VOLUME:-xf_dell_rust}"
WORKDIR="${DELL_RUST_WORKDIR:-rust}"
IMAGE="xf-linker-compiled-mutation-tools:latest"

. scripts/_dell_only_guard.sh
xf_require_remote_context dell-rust "$CTX"
if ! xf_remote_context_reachable "$CTX"; then
  echo "FAIL dell-rust: Dell context '$CTX' is required and not reachable." >&2
  echo "WHY: Rust builds/tests/benches run on the Dell helper only; no Windows fallback." >&2
  echo "UNBLOCK: wake/fix the Dell Docker context, then re-run." >&2
  exit 1
fi

# Sync the Rust workspace + toolchain pin into the Dell volume. Only the roots
# cargo needs are shipped; build artefacts (target/) and caches are excluded.
roots=(rust rust-toolchain.toml)
existing=()
for r in "${roots[@]}"; do [[ -e "$r" ]] && existing+=("$r"); done
if ! tar -cf - --exclude=target --exclude=.git "${existing[@]}" \
    | python scripts/remote_docker.py --host "$CTX" -- run --rm -i -v "$VOL":/repo \
        alpine:latest sh -c "rm -rf /repo/rust /repo/rust-toolchain.toml && tar -xf - -C /repo"; then
  echo "FAIL dell-rust: could not sync the Rust workspace to Dell." >&2
  exit 1
fi

exec python scripts/remote_docker.py --host "$CTX" -- run --rm \
  -v "$VOL":/repo \
  -v xf_sccache:/sccache \
  -e RUSTC_WRAPPER=sccache \
  -e SCCACHE_DIR=/sccache \
  -e CARGO_TERM_COLOR=never \
  -w "/repo/$WORKDIR" \
  "$IMAGE" cargo "$@"
